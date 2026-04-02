"""
ARIA pre-screening interview prompts.

Designed for speed — prompts are concise to minimize LLM latency.
The engine passes CURRENT_SKILL with its RULE (angle, resume_evidence, sample_question)
so the LLM knows exactly what to ask about and from what angle.
"""

from typing import Any
from backend.interview.state import InterviewState


# ─────────────────────────────────────────────────────────────────
# System prompt — kept SHORT for faster LLM response
# ─────────────────────────────────────────────────────────────────

ARIA_SYSTEM = """\
You are ARIA, a friendly AI pre-screening interviewer. Keep it warm,
natural, and conversational — like a senior colleague chatting over coffee.

RULES:
- ONE question per turn, 1-2 sentences max
- Each skill has a SPECIFIC ANGLE — ask about that angle, not generically
- BREADTH over depth — get a signal on each skill, then move on
- Reference what the candidate said, don't parrot their resume
- Natural transitions between topics
- Never say "Can you walk me through..."
- Understand Tagalog/Taglish but always reply in English
- If candidate says "I don't know" → acknowledge, move on
- Sound natural when spoken aloud — use contractions
- Output ONLY spoken text — no markdown, no labels, no quotes
"""


# ─────────────────────────────────────────────────────────────────
# Greeting
# ─────────────────────────────────────────────────────────────────

def build_greeting_prompt(state: InterviewState) -> str:
    """Short greeting prompt."""
    name = state.candidate_address or (state.candidate_name or "there").split()[0]
    return (
        f"Write a 2-3 sentence greeting for {name}. "
        f"Role: {state.job_title or 'the position'}"
        f"{' at ' + state.company if state.company else ''}. "
        "Introduce yourself as ARIA, mention the role, keep it relaxed, "
        "then ask them to tell you about themselves. "
        "Output spoken text only — no quotes, no markdown."
    )


# ─────────────────────────────────────────────────────────────────
# Turn prompt — combined evaluate + respond  
# ─────────────────────────────────────────────────────────────────

def build_turn_prompt(
    state: InterviewState,
    candidate_text: str,
    covered_skills: list[str],
    uncovered_skills: list[str],
    current_skill: str | None,
    current_skill_entry: dict[str, Any] | None,
    upcoming_skills: list[str],
    upcoming_entries: list[dict[str, Any]],
    is_intro: bool = False,
) -> str:
    """Build the per-turn prompt with skill rules for distinct questions."""

    addr = state.candidate_address or (state.candidate_name or "candidate").split()[0]

    # Last 8 turns for context (fewer = faster)
    history = ""
    for t in state.conversation_history[-8:]:
        role = "ARIA" if t.role == "aria" else "CANDIDATE"
        history += f"{role}: {t.content}\n"
    if not history:
        history = "(none)\n"

    remaining = state.max_questions - state.question_count

    if is_intro:
        # First turn — candidate just introduced themselves
        first_skill = current_skill or (state.required_skills[0] if state.required_skills else "their background")
        first_entry = current_skill_entry or {}
        angle = first_entry.get("angle", "general proficiency")
        sample_q = first_entry.get("sample_question", "")
        resume_evidence = first_entry.get("resume_evidence", "")
        
        return (
            f"Candidate just introduced themselves (not scored).\n"
            f"Name: {addr} | Role: {state.job_title or 'the position'}\n\n"
            f"FIRST SKILL TO ASK: {first_skill}\n"
            f"ANGLE: {angle}\n"
            f"RESUME EVIDENCE: {resume_evidence or 'None found'}\n"
            f"SAMPLE QUESTION: {sample_q or 'Ask about their experience'}\n\n"
            f"INTRO: \"{candidate_text[:400]}\"\n\n"
            f"Pick something from their intro and connect it to {first_skill}, "
            f"focusing on the {angle} angle. Use the sample question as inspiration.\n\n"
            "Reply JSON:\n"
            '{"score":0,"skill_area":"Introduction","feedback":"not scored",'
            '"action":"first_question","wants_to_end":false,'
            '"aria_response":"your question here"}'
        )

    # Normal turn — build skill rule context
    entry = current_skill_entry or {}
    current_angle = entry.get("angle", "general proficiency")
    current_evidence = entry.get("resume_evidence", "")
    current_sample = entry.get("sample_question", "")

    # Build upcoming skills with their angles
    next_skills_context = ""
    for ue in upcoming_entries[:3]:
        next_skills_context += f"  - {ue.get('skill', '?')}: {ue.get('angle', 'general')}\n"
    if not next_skills_context:
        next_skills_context = "  (wrap up)"

    covered_str = ", ".join(covered_skills[-6:]) if covered_skills else "none"

    # Score summary (last 3 only)
    recent_lines = []
    for s in state.scores[-3:]:
        recent_lines.append(f"  {s.get('skill_area','?')}: {s.get('score','?')}/10")
    recent_block = "Recent scores:\n" + "\n".join(recent_lines) + "\n" if recent_lines else ""

    return (
        f"Role: {state.job_title or 'the position'} | Candidate: {addr}\n"
        f"Turn {state.question_count}/{state.max_questions} ({remaining} left)\n\n"
        f"CURRENT SKILL: {current_skill or 'wrap up'}\n"
        f"  ANGLE: {current_angle}\n"
        f"  RESUME EVIDENCE: {current_evidence or 'None'}\n"
        f"  SAMPLE Q: {current_sample or 'N/A'}\n\n"
        f"NEXT SKILLS:\n{next_skills_context}\n"
        f"ALREADY COVERED (DO NOT ASK AGAIN): {covered_str}\n"
        f"{recent_block}\n"
        f"CONVERSATION:\n{history}\n"
        f"CANDIDATE: \"{candidate_text[:500]}\"\n\n"
        "INSTRUCTIONS:\n"
        f"1. Score 1-10 (content only, ignore filler/nervousness)\n"
        f"2. Your question MUST be about the CURRENT SKILL's ANGLE (not generic)\n"
        f"3. If action=move_on, ask about the FIRST skill in NEXT SKILLS using its angle\n"
        f"4. If action=follow_up, dig deeper into the CURRENT SKILL's angle (max 1 follow-up)\n"
        f"5. NEVER ask about already covered skills: {covered_str}\n"
        f"6. Use the sample question as inspiration but make it conversational\n"
        f"7. Keep response to 1-2 sentences\n\n"
        "Reply JSON:\n"
        '{"score":7,"skill_area":"Specific Skill",'
        '"feedback":"brief note",'
        '"action":"move_on or follow_up",'
        '"wants_to_end":false,'
        '"aria_response":"your spoken response"}'
    )


# ─────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────

def build_verdict_prompt(state: InterviewState, avg_score: float) -> str:
    """Build verdict prompt."""
    qa_lines = []
    for s in state.scores:
        if s.get("score", 0) > 0:
            qa_lines.append(
                f"- {s.get('skill_area','?')} ({s.get('score','?')}/10): "
                f"{s.get('feedback','')}"
            )
    qa_text = "\n".join(qa_lines) if qa_lines else "No scored answers."

    logistics = []
    if state.salary_expectation:
        logistics.append(f"Salary: {state.salary_expectation}")
    if state.availability:
        logistics.append(f"Availability: {state.availability}")
    if state.work_arrangement:
        logistics.append(f"Work: {state.work_arrangement}")
    log_text = "; ".join(logistics) if logistics else "Not discussed"

    scored = [s for s in state.scores if s.get("score", 0) > 0]

    return (
        f"Pre-screening verdict for recruiter.\n\n"
        f"Candidate: {state.candidate_name or 'Unknown'}\n"
        f"Role: {state.job_title or 'the position'}\n"
        f"Match: {state.match_score}% | Avg score: {avg_score}/10 ({len(scored)} Qs)\n"
        f"Required: {', '.join(state.required_skills[:8]) if state.required_skills else 'N/A'}\n"
        f"Gaps: {', '.join(state.missing_skills[:5]) if state.missing_skills else 'none'}\n\n"
        f"Scores:\n{qa_text}\n\n"
        f"Logistics: {log_text}\n\n"
        "Reply JSON:\n"
        '{"overall_verdict":"Strong Hire|Hire|Maybe|No Hire",'
        f'"overall_score":{avg_score},'
        '"strengths":["..."],"concerns":["..."],'
        '"recommendation":"2-3 sentence summary",'
        '"skill_scores":{"technical":7,"communication":7,"problem_solving":7},'
        '"logistics_fit":{"salary_alignment":"...","availability_fit":"..."}}'
    )
