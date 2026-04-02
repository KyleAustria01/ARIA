"""
ARIA Pre-Screening Interview Engine.

Dynamic, skill-queue-driven interview engine.
- Builds an interview plan from the JD skills at runtime (not hardcoded)
- Enforces topic progression with a skill queue (each skill gets 1-2 turns max)
- Detects candidate repetition callouts and immediately switches topics
- ONE LLM call per turn (evaluate + respond combined)
- Pure Python routing — no LLM decides when to end

Works with ANY JD / resume pair — nothing is role-specific or hardcoded.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import settings
from backend.interview.prompts import (
    ARIA_SYSTEM,
    build_greeting_prompt,
    build_turn_prompt,
    build_verdict_prompt,
)
from backend.interview.state import ConversationTurn, InterviewState
from backend.llm.provider import llm_invoke

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────

_MAX_TURNS_PER_SKILL = 2      # max turns on any single skill before forced move
_ABSOLUTE_MAX_TURNS = 10      # safety net — interview ends no matter what

# Phrases that indicate candidate noticed repetition
_REPETITION_PHRASES = [
    "same question", "asked that", "already answered", "you already",
    "asked me that", "same thing", "repeat", "duplicate",
    "been asked", "earlier question", "previous question",
]


@dataclass
class TurnResult:
    """Result of processing one candidate turn."""
    aria_text: str
    score_entry: dict
    should_end: bool


# ─────────────────────────────────────────────────────────────────
# JSON parsing
# ─────────────────────────────────────────────────────────────────

def _safe_json(text: str, fallback: dict | None = None) -> dict:
    """Parse JSON from LLM output, tolerating markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return fallback or {}


# ─────────────────────────────────────────────────────────────────
# Skill similarity — lightweight, no external deps
# ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> set[str]:
    """Tokenize and lowercase for comparison."""
    return set(re.findall(r"[a-z0-9+#]+", text.lower()))


def _is_similar(a: str, b: str) -> bool:
    """Check if two skill/topic strings are semantically similar."""
    ta, tb = _normalize(a), _normalize(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    smaller = min(len(ta), len(tb))
    return overlap / smaller >= 0.5 if smaller > 0 else False


# ─────────────────────────────────────────────────────────────────
# Interview Engine
# ─────────────────────────────────────────────────────────────────

class InterviewEngine:
    """Dynamic, skill-queue-driven pre-screening interview engine.

    The engine builds an interview plan from the JD's required_skills
    at init time. Each skill gets 1-2 turns max, then the engine
    advances to the next skill in the queue — regardless of what the
    LLM wants to do.

    Usage:
        engine = InterviewEngine(state)
        greeting = await engine.generate_greeting()
        result = await engine.process_turn(candidate_text)
        if result.should_end:
            questions = engine.build_closing_questions()
            await engine.extract_logistics()
            verdict = await engine.generate_verdict()
    """

    def __init__(self, state: InterviewState) -> None:
        self.state = state

        # Build skill_rules lookup by skill name
        self._skill_rules_map: dict[str, dict[str, str]] = {}
        for rule in state.skill_rules:
            skill = rule.get("skill", "")
            if skill:
                self._skill_rules_map[skill.lower()] = rule

        # Build skill queue from JD — the ordered list of skills to cover.
        # Each entry: {"skill": str, "turns_spent": int, "rule": dict}
        self._skill_queue: list[dict[str, Any]] = []
        for skill in state.required_skills:
            rule = self._skill_rules_map.get(skill.lower(), {})
            self._skill_queue.append({
                "skill": skill,
                "turns_spent": 0,
                "angle": rule.get("angle", "general proficiency"),
                "resume_evidence": rule.get("resume_evidence", ""),
                "sample_question": rule.get("sample_question", ""),
            })
        # Append nice-to-have at the end if time permits
        for skill in state.nice_to_have_skills:
            if not any(s["skill"] == skill for s in self._skill_queue):
                rule = self._skill_rules_map.get(skill.lower(), {})
                self._skill_queue.append({
                    "skill": skill,
                    "turns_spent": 0,
                    "angle": rule.get("angle", "general proficiency"),
                    "resume_evidence": rule.get("resume_evidence", ""),
                    "sample_question": rule.get("sample_question", ""),
                })

        # Pointer to current position in the queue
        self._current_skill_idx: int = 0

        # Restore queue position from existing scores (for resume/reconnect)
        if state.scores:
            self._restore_queue_position()

    def _restore_queue_position(self) -> None:
        """Advance the queue pointer based on already-scored turns."""
        covered_areas = set()
        for s in self.state.scores:
            area = s.get("skill_area", "")
            if area and area not in ("General", "Introduction"):
                covered_areas.add(area)

        # Mark skills as spent and advance pointer
        for i, entry in enumerate(self._skill_queue):
            for area in covered_areas:
                if _is_similar(entry["skill"], area):
                    entry["turns_spent"] = _MAX_TURNS_PER_SKILL
                    break
            # Advance pointer past fully covered skills
            if entry["turns_spent"] >= _MAX_TURNS_PER_SKILL:
                if i >= self._current_skill_idx:
                    self._current_skill_idx = i + 1

    # ── Queue helpers ────────────────────────────────────────────

    def _current_skill(self) -> str | None:
        """Get the current skill being assessed, or None if queue exhausted."""
        while self._current_skill_idx < len(self._skill_queue):
            entry = self._skill_queue[self._current_skill_idx]
            if entry["turns_spent"] < _MAX_TURNS_PER_SKILL:
                return entry["skill"]
            self._current_skill_idx += 1
        return None

    def _current_skill_entry(self) -> dict[str, Any] | None:
        """Get the full entry for current skill including rule context."""
        while self._current_skill_idx < len(self._skill_queue):
            entry = self._skill_queue[self._current_skill_idx]
            if entry["turns_spent"] < _MAX_TURNS_PER_SKILL:
                return entry
            self._current_skill_idx += 1
        return None

    def _advance_skill(self) -> str | None:
        """Force-advance to the next skill in the queue. Returns the new skill."""
        if self._current_skill_idx < len(self._skill_queue):
            self._skill_queue[self._current_skill_idx]["turns_spent"] = _MAX_TURNS_PER_SKILL
        self._current_skill_idx += 1
        return self._current_skill()

    def _record_turn_on_skill(self, skill_area: str) -> None:
        """Record that a turn was spent discussing a skill area."""
        # Find the queue entry that best matches
        for entry in self._skill_queue:
            if _is_similar(entry["skill"], skill_area):
                entry["turns_spent"] += 1
                return
        # If no match, increment current skill's counter anyway
        if self._current_skill_idx < len(self._skill_queue):
            self._skill_queue[self._current_skill_idx]["turns_spent"] += 1

    def _get_covered_and_uncovered(self) -> tuple[list[str], list[str]]:
        """Get covered and uncovered skills based on queue state."""
        covered = []
        uncovered = []
        for entry in self._skill_queue:
            if entry["turns_spent"] > 0:
                covered.append(entry["skill"])
            else:
                uncovered.append(entry["skill"])
        return covered, uncovered

    def _upcoming_skills(self, n: int = 3) -> list[str]:
        """Get the next N skills in the queue that haven't been fully covered."""
        result = []
        for i in range(self._current_skill_idx, len(self._skill_queue)):
            entry = self._skill_queue[i]
            if entry["turns_spent"] < _MAX_TURNS_PER_SKILL:
                result.append(entry["skill"])
                if len(result) >= n:
                    break
        return result

    def _upcoming_skill_entries(self, n: int = 3) -> list[dict[str, Any]]:
        """Get the next N skill entries with full rule context."""
        result = []
        for i in range(self._current_skill_idx, len(self._skill_queue)):
            entry = self._skill_queue[i]
            if entry["turns_spent"] < _MAX_TURNS_PER_SKILL:
                result.append(entry)
                if len(result) >= n:
                    break
        return result

    # ── Repetition detection ─────────────────────────────────────

    def _candidate_flagged_repetition(self, text: str) -> bool:
        """Check if the candidate is calling out that ARIA is repeating."""
        low = text.lower()
        return any(phrase in low for phrase in _REPETITION_PHRASES)

    # ── Greeting ─────────────────────────────────────────────────

    async def generate_greeting(self) -> str:
        """Generate ARIA's opening greeting."""
        prompt = build_greeting_prompt(self.state)
        addr = self.state.candidate_address or (
            self.state.candidate_name or "there"
        ).split()[0]

        try:
            text = await llm_invoke([
                {"role": "system", "content": ARIA_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            text = text.strip().strip('"')
        except Exception as e:
            logger.warning("Greeting LLM failed (%s), using fallback", e)
            text = (
                f"Hi {addr}, I'm ARIA and I'll be handling your pre-screening "
                f"today for the {self.state.job_title or 'open'} position"
                f"{' at ' + self.state.company if self.state.company else ''}. "
                "Let's keep this conversational — could you tell me a bit "
                "about yourself and your recent work?"
            )

        self.state.conversation_history.append(
            ConversationTurn(role="aria", content=text, timestamp=time.time())
        )
        self.state.interview_started_at = time.time()
        logger.info("Greeting: %s", text[:120])
        return text

    # ── Core turn processing ─────────────────────────────────────

    async def process_turn(self, candidate_text: str) -> TurnResult:
        """Process one candidate turn. ONE LLM call.

        1. Check for repetition callout → force topic switch
        2. Ask LLM to evaluate + respond
        3. Verify LLM actually switched topics (override if not)
        4. Advance skill queue
        5. Check end conditions
        """
        # Record candidate turn
        self.state.conversation_history.append(
            ConversationTurn(role="applicant", content=candidate_text, timestamp=time.time())
        )

        # is_intro = first response from candidate (their self-introduction)
        # question_count starts at 0, becomes 1 after intro is processed
        is_intro = self.state.question_count == 0
        covered, uncovered = self._get_covered_and_uncovered()
        current_skill = self._current_skill()
        current_skill_entry = self._current_skill_entry()
        upcoming = self._upcoming_skills(3)
        upcoming_entries = self._upcoming_skill_entries(3)

        # ── Check if candidate flagged repetition ──
        repetition_detected = self._candidate_flagged_repetition(candidate_text)
        if repetition_detected and not is_intro:
            logger.warning("Candidate flagged repetition — forcing topic switch")
            next_skill = self._advance_skill()
            next_entry = self._current_skill_entry()
            if next_skill and next_entry:
                # Use the sample_question if available
                sample_q = next_entry.get("sample_question", "")
                if sample_q:
                    aria_text = f"You're right, I apologize for that. {sample_q}"
                else:
                    aria_text = (
                        f"You're right, I apologize for circling back on that. "
                        f"Let's move on — how has your experience been with {next_skill}?"
                    )
            else:
                aria_text = (
                    "You're right, my apologies. Let me ask about something "
                    "different — what's a recent technical challenge you tackled "
                    "that you're proud of?"
                )

            self.state.question_count += 1
            score_entry = {
                "score": 0, "skill_area": "Repetition Detected",
                "feedback": "Candidate flagged repetition — skipped",
                "action": "move_on", "forced_switch": True,
                "question": self._last_aria_text(), "answer": candidate_text,
            }
            self.state.conversation_history.append(
                ConversationTurn(role="aria", content=aria_text, timestamp=time.time())
            )
            should_end = self._should_end(False)
            return TurnResult(aria_text=aria_text, score_entry=score_entry, should_end=should_end)

        # ── Build prompt with queue context + skill rules ──
        prompt = build_turn_prompt(
            state=self.state,
            candidate_text=candidate_text,
            covered_skills=covered,
            uncovered_skills=uncovered,
            current_skill=current_skill,
            current_skill_entry=current_skill_entry,
            upcoming_skills=upcoming,
            upcoming_entries=upcoming_entries,
            is_intro=is_intro,
        )

        try:
            raw = await llm_invoke([
                {"role": "system", "content": ARIA_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            result = _safe_json(raw)
        except Exception as e:
            logger.error("process_turn LLM failed: %s", e)
            result = {}

        # Extract LLM response
        aria_text = result.get("aria_response", "").strip().strip('"')
        score_val = int(result.get("score", 0 if is_intro else 5))
        skill_area = result.get("skill_area", current_skill or "General")
        action = result.get("action", "move_on")
        wants_to_end = bool(result.get("wants_to_end", False))

        # ── Python-enforced topic progression ──
        forced_switch = False
        if not is_intro:
            # Record this turn against the matched skill
            self._record_turn_on_skill(skill_area)

            # Check if current skill is now exhausted
            cur = self._current_skill()
            if cur is None or (
                self._current_skill_idx < len(self._skill_queue)
                and self._skill_queue[self._current_skill_idx]["turns_spent"] >= _MAX_TURNS_PER_SKILL
            ):
                # Force advance regardless of what LLM says
                next_skill = self._advance_skill()
                next_entry = self._current_skill_entry()
                if next_skill and action != "move_on":
                    forced_switch = True
                    action = "move_on"
                    # Use sample_question from skill rule if available
                    sample_q = next_entry.get("sample_question", "") if next_entry else ""
                    if sample_q:
                        aria_text = f"Thanks for that. {sample_q}"
                    else:
                        aria_text = (
                            f"Thanks for that. Let's switch gears — "
                            f"tell me about your experience with {next_skill}."
                        )
                    logger.info("Forced move to skill: %s", next_skill)

            # Even if LLM says follow_up, check if skill_area is similar to
            # something we already spent 2+ turns on → override
            if action == "follow_up" and not forced_switch:
                for entry in self._skill_queue:
                    if entry["turns_spent"] >= _MAX_TURNS_PER_SKILL and _is_similar(entry["skill"], skill_area):
                        next_skill = self._advance_skill()
                        next_entry = self._current_skill_entry()
                        if next_skill:
                            forced_switch = True
                            action = "move_on"
                            sample_q = next_entry.get("sample_question", "") if next_entry else ""
                            if sample_q:
                                aria_text = f"That's great context. {sample_q}"
                            else:
                                aria_text = (
                                    f"That's great context. Now, how about {next_skill} "
                                    f"— what's been your experience there?"
                                )
                        break

        # Fallback for empty response — use sample_question if available
        if not aria_text:
            ns_entry = self._current_skill_entry()
            if ns_entry:
                sample_q = ns_entry.get("sample_question", "")
                if sample_q:
                    aria_text = sample_q
                else:
                    aria_text = f"Tell me about your experience with {ns_entry['skill']}."
            else:
                aria_text = "What's a recent project you're particularly proud of?"

        # Build score entry
        last_aria = self._last_aria_text()
        score_entry = {
            "score": score_val,
            "skill_area": skill_area,
            "feedback": result.get("feedback", ""),
            "action": action,
            "forced_switch": forced_switch,
            "detected_language": result.get("detected_language", "en"),
            "question": last_aria,
            "answer": candidate_text,
        }

        # Store score (skip intro)
        if not is_intro:
            self.state.scores.append(score_entry)

        # Track covered skill areas
        if skill_area and skill_area not in ("General", "Introduction"):
            if skill_area not in self.state.covered_skill_areas:
                self.state.covered_skill_areas.append(skill_area)

        # Always increment — every turn counts
        if is_intro:
            self.state.question_count = 1
        else:
            self.state.question_count += 1

        should_end = self._should_end(wants_to_end)

        # Record ARIA's response
        self.state.conversation_history.append(
            ConversationTurn(role="aria", content=aria_text, timestamp=time.time())
        )

        logger.info(
            "Turn Q%d/%d: score=%s skill=%s action=%s forced=%s end=%s | %s",
            self.state.question_count, self.state.max_questions,
            score_val, skill_area, action, forced_switch, should_end,
            aria_text[:80],
        )

        return TurnResult(aria_text=aria_text, score_entry=score_entry, should_end=should_end)

    # ── End conditions ───────────────────────────────────────────

    def _should_end(self, wants_to_end: bool) -> bool:
        """Decide if the interview should end."""
        if self.state.question_count >= self.state.max_questions:
            return True
        if self.state.question_count >= _ABSOLUTE_MAX_TURNS:
            return True
        # Queue exhausted — all skills covered
        if self._current_skill() is None and self.state.question_count >= 3:
            return True
        # Candidate wants out and we have enough data
        if wants_to_end and self.state.question_count >= 4:
            return True
        return False

    # ── Helpers ──────────────────────────────────────────────────

    def _last_aria_text(self) -> str:
        """Get the last thing ARIA said."""
        for turn in reversed(self.state.conversation_history):
            if turn.role == "aria":
                return turn.content
        return ""

    # ── Closing logistics ────────────────────────────────────────

    def build_closing_questions(self) -> list[str]:
        """Build practical closing questions from JD context."""
        questions: list[str] = []

        questions.append(
            "Before we wrap up, a few quick practical questions. "
            "What's your availability — when could you start?"
        )

        if self.state.salary_range:
            questions.append(
                f"The role lists {self.state.salary_range}. "
                "Does that range work for you?"
            )
        else:
            questions.append("What are your salary expectations for this role?")

        if self.state.location or self.state.employment_type:
            ctx = f"{self.state.location or ''} {self.state.employment_type or ''}".strip()
            questions.append(
                f"This position is {ctx}. "
                "What's your preference — remote, hybrid, or on-site?"
            )
        else:
            questions.append("What's your preferred work arrangement?")

        return questions

    async def extract_logistics(self) -> dict:
        """Extract structured logistics from Q&A."""
        if not self.state.logistics_raw:
            return {}

        qa_text = "\n".join(
            f"Q: {p.get('question', '')}\nA: {p.get('answer', '')}"
            for p in self.state.logistics_raw
        )

        prompt = (
            f"Extract logistics from this Q&A. Reply JSON only:\n\n{qa_text}\n\n"
            '{"salary_expectation":"...","availability":"...",'
            '"work_arrangement":"...","notice_period":"..."}'
        )

        try:
            raw = await llm_invoke([{"role": "user", "content": prompt}])
            parsed = _safe_json(raw, {})
        except Exception as e:
            logger.error("extract_logistics failed: %s", e)
            parsed = {}

        for key in ("salary_expectation", "availability", "work_arrangement",
                     "schedule_preference", "notice_period"):
            setattr(self.state, key, parsed.get(key, ""))

        return parsed

    # ── Final verdict ────────────────────────────────────────────

    async def generate_verdict(self) -> dict:
        """Generate final interview verdict."""
        scores = [float(s.get("score", 5)) for s in self.state.scores if s.get("score", 0) > 0]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0

        prompt = build_verdict_prompt(self.state, avg)

        try:
            raw = await llm_invoke([
                {"role": "system", "content": "You are an expert interview evaluator. Reply JSON only."},
                {"role": "user", "content": prompt},
            ])
            verdict = _safe_json(raw, {"overall_verdict": "Maybe", "recommendation": "Could not generate."})
        except Exception as e:
            logger.error("generate_verdict failed: %s", e)
            verdict = {"overall_verdict": "Maybe", "recommendation": "Evaluation could not be completed."}

        verdict.update({
            "overall_score": avg,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "questions_asked": len(scores),
            "candidate_name": self.state.candidate_name,
            "job_title": self.state.job_title,
            "match_score": self.state.match_score,
            "matched_skills": self.state.matched_skills,
            "missing_skills": self.state.missing_skills,
            "scores": self.state.scores,
            "salary_expectation": self.state.salary_expectation,
            "availability": self.state.availability,
            "work_arrangement": self.state.work_arrangement,
            "schedule_preference": self.state.schedule_preference,
            "notice_period": self.state.notice_period,
        })

        self.state.verdict = verdict
        self.state.is_complete = True
        self.state.interview_ended_at = time.time()
        logger.info("Verdict: %s (avg %.1f)", verdict.get("overall_verdict"), avg)
        return verdict

    # ── Research ─────────────────────────────────────────────────

    async def run_research(self) -> None:
        """Optional Tavily web research."""
        if not settings.tavily_api_key:
            logger.info("Tavily key not set — skipping research")
            return
        try:
            from tavily import TavilyClient
        except ImportError:
            logger.warning("tavily-python not installed — skipping research")
            return

        job = self.state.job_title or "Software Developer"
        skills = ", ".join(self.state.required_skills[:5])
        queries = [f"{job} interview questions"]
        if skills:
            queries.append(f"{skills} interview assessment")

        client = TavilyClient(api_key=settings.tavily_api_key)
        chunks: list[str] = []
        for q in queries:
            try:
                results = client.search(query=q, max_results=3)
                for r in results.get("results", []):
                    content = r.get("content", "").strip()
                    if content:
                        chunks.append(content)
            except Exception as e:
                logger.warning("Tavily query failed: %s", e)

        self.state.research_context = "\n\n".join(chunks)
        logger.info("Research: %d chunks, %d chars", len(chunks), len(self.state.research_context))

    def build_interview_context(self) -> None:
        """Build merged interview context from JD + resume + research."""
        parts: list[str] = []

        jd = [f"ROLE: {self.state.job_title or 'Not specified'}"]
        if self.state.company:
            jd.append(f"COMPANY: {self.state.company}")
        if self.state.required_skills:
            jd.append(f"REQUIRED: {', '.join(self.state.required_skills)}")
        if self.state.nice_to_have_skills:
            jd.append(f"NICE TO HAVE: {', '.join(self.state.nice_to_have_skills)}")
        if self.state.responsibilities:
            jd.append("RESPONSIBILITIES: " + "; ".join(self.state.responsibilities[:6]))
        parts.append("=== JOB ===\n" + "\n".join(jd))

        cand = [f"CANDIDATE: {self.state.candidate_name or 'Unknown'}"]
        if self.state.current_role:
            cand.append(f"CURRENT: {self.state.current_role}")
        if self.state.candidate_skills:
            cand.append(f"SKILLS: {', '.join(self.state.candidate_skills)}")
        if self.state.matched_skills:
            cand.append(f"MATCHED: {', '.join(self.state.matched_skills)}")
        if self.state.missing_skills:
            cand.append(f"GAPS: {', '.join(self.state.missing_skills)}")
        parts.append("=== CANDIDATE ===\n" + "\n".join(cand))

        if self.state.research_context:
            parts.append("=== RESEARCH ===\n" + self.state.research_context[:1500])

        self.state.interview_context = "\n\n".join(parts)

    def get_state_dict(self) -> dict:
        """Return state as dict for Redis."""
        return self.state.model_dump()
