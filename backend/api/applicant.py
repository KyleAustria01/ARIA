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

