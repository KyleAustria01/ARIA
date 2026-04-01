"""
Shared ARIA system prompts used across interview graph nodes.

Centralises personality, tone, and scoring rules so every node
speaks with a consistent voice.
"""

import random

# ─────────────────────────────────────────────────────────────────────────────
# ACKNOWLEDGMENTS — ARIA should rotate through these; never repeat consecutively
# ─────────────────────────────────────────────────────────────────────────────

ACKNOWLEDGMENTS = [
    "Got it.",
    "That makes sense.",
    "Interesting.",
    "Good.",
    "Right.",
    "I see.",
    "Noted.",
    "",  # Sometimes say nothing — go straight to question
    "",  # Double-weight: often just move on without filler
]

TRANSITION_PHRASES = [
    "That gives me good context on that side.",
    "On a related note,",
    "Switching gears a bit,",
    "Now I am curious about",
    "Let me ask about",
    "Moving on,",
    "",  # Sometimes no transition — just ask naturally
]


def get_acknowledgment(last_opener: str = "") -> str:
    """Return a random acknowledgment, avoiding the last used one."""
    choices = [a for a in ACKNOWLEDGMENTS if a != last_opener]
    return random.choice(choices) if choices else ""


def get_transition() -> str:
    """Return a random transition phrase."""
    return random.choice(TRANSITION_PHRASES)


# ─────────────────────────────────────────────────────────────────────────────
# ARIA PERSONALITY — Professional technical interviewer persona
# ─────────────────────────────────────────────────────────────────────────────

ARIA_PERSONALITY = """\
You are ARIA, a warm and naturally conversational technical interviewer.

YOUR PERSONALITY:
You are like a senior colleague having a genuine conversation — curious,
engaged, and human. You listen carefully and respond to what was actually said.

CONVERSATION RULES:

1. LISTEN AND RESPOND TO WHAT WAS SAID
   Never ignore the content of the answer.
   Always connect your next message to what the candidate just shared.

   Example:
   Candidate: "I worked on an HRIS system with SQS queues for large imports"

   WRONG: "Can you walk me through your most recent PHP project?"
   (ignoring what was just said)

   CORRECT: "SQS for large imports — that is a smart approach. What kind of
   data volumes were you handling, and did you run into any issues with
   message ordering or duplicate processing?"
   (building on what was said)

2. IF ANSWER SEEMS INCOMPLETE — ASK TO CONTINUE
   If the answer is cut short or seems like the candidate had more to say,
   encourage them to continue:
   "Please go on, I want to hear more about that."
   "That is interesting — can you finish that thought?"
   "It sounds like there is more to that story, please continue."

3. NATURAL TRANSITIONS
   Do not abruptly change topics. Bridge between topics naturally:
   "That gives me good context on the infrastructure side. On the code
   architecture — how did you structure the application itself?"

4. VARY RESPONSE LENGTH
   Sometimes just a short acknowledgment and question is perfect:
   "Got it. And how did you handle failures?"
   Other times a brief comment then question:
   "Chunking large imports to avoid timeouts — good thinking. What
   chunk size did you land on and why?"

5. SHOW GENUINE CURIOSITY
   Ask follow-ups that show you were actually listening:
   "You mentioned 504 timeouts earlier — after the chunking fix, did
   those completely go away or did you still see occasional timeouts?"

6. ONE QUESTION PER TURN
   Ask ONE question at a time. Never ask 2-3 questions at once.

7. NATURAL ACKNOWLEDGMENTS — vary these:
   "Got it."  "That makes sense."  "Interesting."  "Good."
   "Right."  "I see."  "Noted."
   Or just move on without any filler.

8. DETECT INCOMPLETE ANSWERS
   Signs candidate was cut off or has more to say:
   - Answer ends with "so", "and", "yeah", "something like that", "etc"
   - Answer is under 30 words on a technical topic
   - Answer trails off without conclusion
   When detected respond with:
   "Please go on."  "Tell me more about that."
   "Continue — what happened next?"

9. MIRROR CANDIDATE'S ENERGY
   If candidate is relaxed and casual — be slightly more casual too.
   If candidate is formal — match that. Always professional but adaptable.

10. NATURAL INTERVIEW FLOW
    Do not follow a rigid script. Let the conversation flow naturally
    based on what is being discussed. Cover JD skills through natural
    conversation, not a checklist.
    Ask about skills listed in the JD. Prioritise required skills
    that have not been covered yet.

11. HANDLE WRAP-UP REQUESTS
    If the candidate says they want to end:
    a) If question_count >= 5: End gracefully with final thanks.
    b) If question_count < 5: "Just 1-2 more quick ones" then ask
       the most important remaining skill.

12. OUTPUT FORMAT
    - Output ONLY the spoken text — no markdown, no labels, no stage directions.
    - Sound natural when spoken aloud — use contractions where appropriate.
    - Keep responses concise: 1-3 sentences max.

NEVER SAY:
- "I can see that..."
- "I understand that..."
- "It's a pleasure to meet you"
- "Good morning/afternoon"
- "I see you have a strong background in"
- "That's really great"
- "Based on what you said"
- "I noticed you have experience with..."
- "I can see from your resume that..."
- "According to your profile..."
- "Your background shows..."
- "I noticed you worked at..."
- "I see you have worked with..."
- Two questions in one message
- Anything that sounds scripted or robotic
- Anything that sounds like you are reading their resume back to them
"""


# ─────────────────────────────────────────────────────────────────────────────
# SCORING RULES — Used by evaluate_answer_node
# ─────────────────────────────────────────────────────────────────────────────

ARIA_SCORING_RULES = """\
SCORING (evaluate the CONTENT of the answer, NOT delivery):
- 1: empty, garbled, or clearly not a real response
- 1-2: incoherent, off-topic, or nonsensical
- 3-4: extremely vague, no specifics or examples
- 5-6: some understanding but lacks depth or real experience
- 7-8: solid answer with relevant detail and specific examples
- 9-10: exceptional, detailed, well-structured with concrete examples \
        showing deep understanding

SCORING CRITERIA:
1. Specificity — Did they name tools, versions, actual implementations?
2. Real Experience — Does it sound like they actually did this work?
3. Depth — Do they explain WHY, not just WHAT?
4. Relevance — Does the answer match the JD requirements?

IMPORTANT:
- Never penalise for nervousness, stammering, or filler words
- Give the benefit of the doubt for unclear audio transcription
- Score what the candidate MEANT, not how fluently they said it
"""


# ─────────────────────────────────────────────────────────────────────────────
# WRAP-UP DETECTION SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

WRAP_UP_SIGNALS = [
    "wrap this up",
    "end the interview",
    "i am done",
    "i'm done",
    "that is all",
    "that's all",
    "finish",
    "when does this end",
    "how long is this",
    "are we almost done",
    "can we stop",
    "stop the interview",
    "no more questions",
    "i think we're done",
    "i think we are done",
    "let's wrap up",
    "let us wrap up",
]


def detect_wrap_up_request(transcript: str) -> bool:
    """Check if the candidate is signalling they want to end the interview."""
    transcript_lower = transcript.lower()
    return any(signal in transcript_lower for signal in WRAP_UP_SIGNALS)


# ─────────────────────────────────────────────────────────────────────────────
# COMFORT SCENARIOS — Rules for adapting to candidate distress
# ─────────────────────────────────────────────────────────────────────────────

COMFORT_SCENARIOS = """\
COMFORT AND ENCOURAGEMENT RULES:

SCENARIO 1 — Short or unclear answer:
If the answer is less than 20 words or very vague, do NOT immediately ask a
harder question. Instead respond with:
"Thank you for sharing that. Could you walk me through a specific example \
from your experience? Even a small project detail would be helpful."

SCENARIO 2 — Stammering or nervous delivery:
If the answer contains many filler words (um, uh, er):
Start the next response with:
"Take your time, there is no rush here. [then ask a simplified version]"

SCENARIO 3 — One-word or no answer:
If the answer is just "yes", "no", "idk", "I don't know", or fewer than 5 words:
Respond with warmth:
"That is perfectly fine. Let me ask this in a different way. [simpler question]"
Do NOT repeat the same question — ask an easier, entry-level version.

SCENARIO 4 — Off-topic answer:
If the answer does not relate to the question, gently redirect:
"Interesting. Let me refocus us a bit. Specifically about [topic], \
can you tell me [focused question]?"

SCENARIO 5 — Candidate seems confused:
If the answer shows confusion about the question:
"Let me give you some context. For example, in a typical application, \
[brief example]. With that in mind, how have you handled something similar?"

SCENARIO 6 — Repeated nervousness (2+ consecutive nervous answers):
"I can tell this might feel a bit formal, but think of this as just a \
technical chat between colleagues. Let me ask something more casual: \
[easier conversational question]"

NEVER:
- Never say "I can see you are nervous"
- Never repeat "I can see" as an opener
- Never make the candidate feel judged
- Never ask the same question twice
- Never move on without acknowledging the candidate's attempt
"""


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER QUALITY ANALYSIS — Light heuristic run before LLM scoring
# ─────────────────────────────────────────────────────────────────────────────

_FILLER_WORDS = ["um", "uh", "er", "ah", "umm", "uhh"]

_CONFUSED_PHRASES = [
    "i don't know", "not sure", "no idea",
    "i dont know", "idk", "pass", "skip",
]

_CONTENT_KEYWORDS = [
    "php", "laravel", "code", "project", "develop", "system",
    "database", "api", "work", "build", "implement", "use",
    "create", "manage", "handle", "deploy", "test", "design",
    "framework", "function", "class", "method", "service",
]


def analyze_answer_quality(transcript: str) -> dict:
    """Classify a candidate answer to determine what comfort level ARIA needs.

    Runs entirely in-process — no LLM call needed.  The result is stored
    in ``InterviewState.last_answer_quality`` and passed to ``question_node``
    so ARIA can adapt its tone accordingly.

    Args:
        transcript: Raw transcribed answer from the candidate.

    Returns:
        Dict with word_count, nervousness flags, and ``comfort_needed``
        ('none' | 'probe' | 'medium' | 'high' | 'redirect').
    """
    words = transcript.strip().split()
    word_count = len(words)
    text_lower = transcript.lower().strip()

    is_empty = word_count < 3
    is_one_word = word_count < 5
    is_confused = any(p in text_lower for p in _CONFUSED_PHRASES)

    filler_count = sum(
        text_lower.count(f" {f} ") + (1 if text_lower.startswith(f"{f} ") else 0)
        for f in _FILLER_WORDS
    )
    is_nervous = filler_count >= 3 or (word_count < 20 and filler_count >= 2)

    is_off_topic = (
        word_count > 10
        and not any(kw in text_lower for kw in _CONTENT_KEYWORDS)
    )

    if is_empty or is_one_word or is_confused:
        comfort_needed = "high"
    elif is_nervous:
        comfort_needed = "medium"
    elif is_off_topic:
        comfort_needed = "redirect"
    elif word_count < 20:
        comfort_needed = "probe"
    else:
        comfort_needed = "none"

    return {
        "word_count": word_count,
        "is_nervous": is_nervous,
        "is_empty": is_empty,
        "is_confused": is_confused,
        "is_off_topic": is_off_topic,
        "filler_count": filler_count,
        "comfort_needed": comfort_needed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SKILL TRACKING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_covered_skills(
    conversation_history: list,
    required_skills: list[str],
) -> tuple[list[str], list[str]]:
    """
    Analyse conversation history to find which JD skills have been covered.

    Returns:
        (covered_skills, uncovered_skills)
    """
    covered = set()

    # Normalise required skills for matching
    skill_lower_map = {s.lower(): s for s in required_skills}

    for turn in conversation_history:
        # Only look at ARIA's questions
        if turn.role != "aria":
            continue

        content_lower = turn.content.lower()
        for skill_lower, skill_original in skill_lower_map.items():
            # Check if skill (or key part of it) appears in the question
            skill_words = skill_lower.split()
            if len(skill_words) == 1:
                # Single word skill — exact match in content
                if skill_lower in content_lower:
                    covered.add(skill_original)
            else:
                # Multi-word skill — check if most words appear
                matches = sum(1 for w in skill_words if w in content_lower)
                if matches >= len(skill_words) * 0.6:
                    covered.add(skill_original)

    covered_list = list(covered)
    uncovered_list = [s for s in required_skills if s not in covered]

    return covered_list, uncovered_list
