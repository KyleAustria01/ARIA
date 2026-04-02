"""
Interview state for ARIA pre-screening system.

Simple Pydantic model — no LangGraph state reducers, no topic-staleness
counters, no nervousness trackers. The engine handles all that through
prompt context, not state fields.
"""

from typing import Any
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """A single turn in the interview conversation."""

    role: str          # "aria" or "applicant"
    content: str       # spoken/transcribed text
    timestamp: float = 0.0


class InterviewState(BaseModel):
    """Full state for an ARIA pre-screening interview session."""

    # Session identity
    session_id: str = ""

    # --- JD data ---
    jd_raw_text: str = ""
    job_title: str = ""
    company: str = ""
    location: str = ""
    employment_type: str = ""
    experience_required: str = ""
    salary_range: str = ""
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)

    # --- Resume data ---
    resume_raw_text: str = ""
    candidate_name: str = ""
    candidate_email: str = ""
    candidate_phone: str = ""
    current_role: str = ""
    total_experience_years: int = 0
    candidate_skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    match_score: int = 0
    match_tier: dict[str, str] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)

    # --- Per-skill interview rules ---
    # Generated at setup time from JD + resume analysis.
    # Each entry: {"skill": str, "angle": str, "resume_evidence": str, "sample_question": str}
    skill_rules: list[dict[str, str]] = Field(default_factory=list)

    # --- Research / context ---
    research_context: str = ""
    interview_context: str = ""

    # --- Candidate identity ---
    candidate_title: str = ""
    candidate_address: str = ""

    # --- Live interview ---
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    question_count: int = 0
    max_questions: int = 8
    scores: list[dict[str, Any]] = Field(default_factory=list)
    covered_skill_areas: list[str] = Field(default_factory=list)
    is_complete: bool = False
    interview_started_at: float = 0.0
    interview_ended_at: float = 0.0

    # --- Logistics (closing questions) ---
    salary_expectation: str = ""
    availability: str = ""
    work_arrangement: str = ""
    schedule_preference: str = ""
    notice_period: str = ""
    logistics_raw: list[dict[str, str]] = Field(default_factory=list)

    # --- Final verdict ---
    verdict: dict[str, Any] = Field(default_factory=dict)

    # --- File paths (temp storage during upload) ---
    jd_file_path: str = ""
    resume_file_path: str = ""


def get_match_tier(score: float) -> dict:
    """Convert a numeric match score to a tier label with color and icon."""
    if score >= 90:
        return {
            "tier": "Excellent Match", "label": "Excellent", "color": "green",
            "description": "Candidate meets all requirements", "icon": "🟢",
        }
    elif score >= 65:
        return {
            "tier": "Good Match", "label": "Good", "color": "blue",
            "description": "Candidate meets most requirements", "icon": "🔵",
        }
    elif score >= 30:
        return {
            "tier": "Partial Match", "label": "Partial", "color": "yellow",
            "description": "Candidate meets some requirements", "icon": "🟡",
        }
    else:
        return {
            "tier": "Low Match", "label": "Low", "color": "red",
            "description": "Candidate may not meet requirements", "icon": "🔴",
        }
