"""
Applicant API endpoints for ARIA MVP 2.0.

No authentication required — session-based flow.
The applicant uses the session_id shared by the recruiter to:
  1. GET pre-join info (name, role, company) before joining.
  2. POST to mark the session as actively joined.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/session/{session_id}")
async def get_pre_join_info(session_id: str) -> Dict[str, Any]:
    """Return publicly-safe pre-join information for the applicant.

    Called by the InterviewPage before the applicant clicks "Join Interview"
    so the UI can show their name, the role, and the company.

    Args:
        session_id: UUID hex string from the invite link.

    Returns:
        Subset of session state safe to expose to the applicant.
    """
    data = await redis_client.get_json(f"session:{session_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Check if there's existing conversation history (for resume detection)
    conversation_history = data.get("conversation_history", [])
    question_count = data.get("question_count", 0)
    is_resuming = len(conversation_history) > 0 and question_count > 0

    return {
        "session_id": session_id,
        "candidate_name": data.get("candidate_name", "Candidate"),
        "job_title": data.get("job_title", ""),
        "company": data.get("company", ""),
        "required_skills": data.get("required_skills", []),
        "max_questions": data.get("max_questions", 7),
        "is_complete": data.get("is_complete", False),
        "is_resuming": is_resuming,
        "question_count": question_count,
        "conversation_history": [
            {"role": turn.get("role", ""), "text": turn.get("content", "")}
            for turn in conversation_history
        ] if is_resuming else [],
    }


@router.post("/join/{session_id}")
async def join_session(session_id: str) -> Dict[str, Any]:
    """Mark a session as joined and set interview_started_at timestamp.

    Call this right before the WebSocket is opened so the state
    correctly records when the interview began.

    Args:
        session_id: UUID hex string from the invite link.

    Returns:
        Confirmation dict with status and session_id.
    """
    data = await redis_client.get_json(f"session:{session_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if data.get("is_complete"):
        raise HTTPException(status_code=409, detail="Interview already completed")

    data["interview_started_at"] = datetime.now(timezone.utc).timestamp()
    await redis_client.set_json(f"session:{session_id}", data)

    return {"status": "joined", "session_id": session_id}


@router.get("/results/{session_id}")
async def get_results(session_id: str) -> Dict[str, Any]:
    """Return interview results for a completed session.

    Args:
        session_id: UUID hex string from the invite link.

    Returns:
        Session data including scores, verdict, and question breakdown.
    """
    data = await redis_client.get_json(f"session:{session_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    return {
        "session_id": session_id,
        "candidate_name": data.get("candidate_name", "Candidate"),
        "job_title": data.get("job_title", ""),
        "company": data.get("company", ""),
        "location": data.get("location", ""),
        "employment_type": data.get("employment_type", ""),
        "salary_range": data.get("salary_range", ""),
        "scores": data.get("scores", []),
        "verdict": data.get("verdict", {}),
        "is_complete": data.get("is_complete", False),
        "question_count": data.get("question_count", 0),
        "max_questions": data.get("max_questions", 8),
        "match_score": data.get("match_score", 0),
        "matched_skills": data.get("matched_skills", []),
        "missing_skills": data.get("missing_skills", []),
        "interview_started_at": data.get("interview_started_at", 0),
        "interview_ended_at": data.get("interview_ended_at", 0),
        # Logistics
        "salary_expectation": data.get("salary_expectation", ""),
        "availability": data.get("availability", ""),
        "work_arrangement": data.get("work_arrangement", ""),
        "notice_period": data.get("notice_period", ""),
        "logistics_raw": data.get("logistics_raw", []),
    }

