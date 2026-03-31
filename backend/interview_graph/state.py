"""
LangGraph state schema for ARIA MVP 2.0.

Defines the full typed state shared across all interview graph nodes.
Each field maps to a stage in the recruiter → applicant → results flow.
"""

from typing import Any
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """A single turn in the interview conversation."""

    role: str          # "aria" or "applicant"
    content: str       # spoken/transcribed text
    timestamp: float = 0.0  # unix timestamp


class ExperienceEntry(BaseModel):
    """One job entry from a parsed resume."""

    company: str = ""
    role: str = ""
    duration: str = ""
    highlights: list[str] = Field(default_factory=list)


class InterviewState(BaseModel):
    """
    Full typed state for the ARIA LangGraph interview pipeline.

    Populated progressively as each node runs:
      recruiter upload → JD analysis → resume analysis →
      research → merge → question loop → final evaluation
    """

    # Session identity
    session_id: str = ""

    # --- JD data (from analyze_jd_node) ---
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

    # --- Resume data (from analyze_resume_node) ---
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

    # --- Research data (from research_node) ---
    research_context: str = ""

    # --- Merged interview context (from merge_context_node) ---
    interview_context: str = ""

    # --- Live interview state ---
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    question_count: int = 0
    max_questions: int = 7
    scores: list[dict[str, Any]] = Field(default_factory=list)
    is_complete: bool = False
    interview_started_at: float = 0.0
    interview_ended_at: float = 0.0

    # --- Candidate logistics (from closing questions) ---
    salary_expectation: str = ""
    availability: str = ""
    work_arrangement: str = ""   # e.g. "remote", "hybrid", "on-site"
    schedule_preference: str = ""  # e.g. "full-time", "part-time", shift info
    notice_period: str = ""
    logistics_raw: list[dict[str, str]] = Field(default_factory=list)  # full Q&A pairs

    # --- Final evaluation (from final_evaluation_node) ---
    verdict: dict[str, Any] = Field(default_factory=dict)

    # --- Emotional intelligence / speech analysis ---
    candidate_title: str = ""          # "Mr.", "Ms.", or "" (unknown)
    candidate_address: str = ""        # Formal address: "Mr. Smith" or "John"
    candidate_nervous: bool = False
    consecutive_nervous_count: int = 0
    elaborate_requested: bool = False
    non_answer_count: int = 0
    speech_quality_history: list[dict[str, Any]] = Field(default_factory=list)

    # --- Wrap-up / interview flow control ---
    candidate_wants_to_end: bool = False       # Candidate signalled end request
    wrap_up_acknowledged: bool = False         # ARIA has acknowledged wrap-up
    last_aria_opener: str = ""                 # Last acknowledgment used (avoid repetition)
    covered_skills: list[str] = Field(default_factory=list)  # Skills already asked about

    # --- File paths (temp storage during upload) ---
    jd_file_path: str = ""
    resume_file_path: str = ""

