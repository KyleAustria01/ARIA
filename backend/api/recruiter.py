"""
Recruiter API endpoints for ARIA MVP 2.0.

No authentication required — session-based flow.
Separate endpoints for JD and resume upload so the recruiter sees
extracted data previews before generating an interview link.

Includes chunked-upload endpoints for large files / slow connections:
  POST /upload/init          – create an upload session
  POST /upload/chunk         – send one chunk
  GET  /upload/status/{id}   – poll processing status
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.interview_graph.analyze_resume_node import get_match_tier
from backend.interview_graph.graph_builder import setup_graph
from backend.interview_graph.state import InterviewState
from backend.redis_client import redis_client
from backend.utils.pdf_parser import parse_jd, parse_resume

logger = logging.getLogger(__name__)

router = APIRouter()

_UPLOAD_DIR = "uploads"
_CHUNK_DIR = os.path.join(_UPLOAD_DIR, "chunks")
os.makedirs(_UPLOAD_DIR, exist_ok=True)
os.makedirs(_CHUNK_DIR, exist_ok=True)


async def _save_upload(file: UploadFile, prefix: str) -> str:
    """Save an uploaded file to disk and return its absolute path."""
    ext = os.path.splitext(file.filename or "")[1] or ".pdf"
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    path = os.path.join(_UPLOAD_DIR, filename)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return os.path.abspath(path)


# ═══════════════════════════════════════════════════════════════════
# Chunked Upload Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post("/upload/init")
async def init_upload(
    file_name: str = Form(...),
    file_size: int = Form(...),
    total_chunks: int = Form(...),
    upload_type: str = Form(...),
    session_id: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Initialise a chunked upload session.

    Args:
        file_name: Original file name.
        file_size: Total file size in bytes.
        total_chunks: Number of chunks the client will send.
        upload_type: ``"jd"`` or ``"resume"``.
        session_id: Existing session id (required for resume uploads).

    Returns:
        ``upload_id`` and ``session_id`` to use for subsequent chunk requests.
    """
    if upload_type not in ("jd", "resume"):
        raise HTTPException(status_code=400, detail="upload_type must be 'jd' or 'resume'")

    upload_id = uuid.uuid4().hex
    effective_session_id = session_id or uuid.uuid4().hex

    upload_meta = {
        "file_name": file_name,
        "file_size": file_size,
        "total_chunks": total_chunks,
        "received_chunks": [],
        "upload_type": upload_type,
        "session_id": effective_session_id,
        "status": "uploading",
    }
    await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)

    return {"upload_id": upload_id, "session_id": effective_session_id}


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
) -> Dict[str, Any]:
    """Receive a single chunk and, once all chunks arrive, trigger assembly.

    Args:
        upload_id: The upload session returned by ``/upload/init``.
        chunk_index: Zero-based index of this chunk.
        total_chunks: Total expected chunks (used for validation).
        chunk: The binary chunk payload.

    Returns:
        Current chunk progress and upload status.
    """
    raw = await redis_client.get(f"upload:{upload_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Upload session not found")

    upload_meta: Dict[str, Any] = json.loads(raw)

    # Validate chunk index
    if chunk_index < 0 or chunk_index >= upload_meta["total_chunks"]:
        raise HTTPException(status_code=400, detail="Invalid chunk_index")

    # Idempotent: skip if already received
    if chunk_index in upload_meta["received_chunks"]:
        return {
            "received": chunk_index,
            "total": upload_meta["total_chunks"],
            "status": upload_meta["status"],
        }

    # Persist chunk to disk
    chunk_path = os.path.join(_CHUNK_DIR, f"{upload_id}_{chunk_index}")
    chunk_data = await chunk.read()
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(chunk_data)

    upload_meta["received_chunks"].append(chunk_index)

    # All chunks received → kick off background assembly + processing
    if len(upload_meta["received_chunks"]) == upload_meta["total_chunks"]:
        upload_meta["status"] = "assembling"
        await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)
        asyncio.create_task(_assemble_and_process(upload_id, upload_meta))
    else:
        await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)

    return {
        "received": chunk_index,
        "total": upload_meta["total_chunks"],
        "status": upload_meta["status"],
    }


@router.get("/upload/status/{upload_id}")
async def get_upload_status(upload_id: str) -> Dict[str, Any]:
    """Poll the current state of a chunked upload.

    Returns the full upload metadata including ``status``,
    and ``result`` once processing is complete.
    """
    raw = await redis_client.get(f"upload:{upload_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Upload not found")
    return json.loads(raw)


# ── Background: assemble chunks → parse → analyse ───────────────────

async def _assemble_and_process(upload_id: str, upload_meta: Dict[str, Any]) -> None:
    """Assemble uploaded chunks into a single PDF then parse and analyse it.

    Runs as a fire-and-forget ``asyncio`` task so the chunk endpoint
    returns immediately. Status updates are pushed into Redis so the
    frontend can poll via ``/upload/status/{upload_id}``.
    """
    try:
        total_chunks = upload_meta["total_chunks"]
        upload_type = upload_meta["upload_type"]
        session_id = upload_meta["session_id"]

        # ── 1. Assemble chunks into one file ─────────────────────────
        output_path = os.path.join(_UPLOAD_DIR, f"{upload_type}_{upload_id}.pdf")
        async with aiofiles.open(output_path, "wb") as outfile:
            for i in range(total_chunks):
                chunk_path = os.path.join(_CHUNK_DIR, f"{upload_id}_{i}")
                async with aiofiles.open(chunk_path, "rb") as cf:
                    await outfile.write(await cf.read())
                os.unlink(chunk_path)

        output_path = os.path.abspath(output_path)

        # ── 2. Update status → analysing ─────────────────────────────
        upload_meta["status"] = "analyzing"
        upload_meta["file_path"] = output_path
        await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)

        # ── 3. Parse & analyse ────────────────────────────────────────
        if upload_type == "jd":
            result = await parse_jd(output_path)

            # Persist a new session with JD data
            state = InterviewState(
                session_id=session_id,
                jd_file_path=output_path,
                jd_raw_text=result.get("raw_text", ""),
                job_title=result.get("job_title", ""),
                company=result.get("company", ""),
                location=result.get("location", ""),
                employment_type=result.get("employment_type", ""),
                experience_required=result.get("experience_required", ""),
                salary_range=result.get("salary_range", ""),
                required_skills=result.get("required_skills", []),
                nice_to_have_skills=result.get("nice_to_have_skills", []),
                responsibilities=result.get("responsibilities", []),
                qualifications=result.get("qualifications", []),
            )
            await redis_client.set_json(f"session:{session_id}", state.model_dump())

            result = {
                "session_id": session_id,
                "job_title": state.job_title,
                "company": state.company,
                "location": state.location,
                "employment_type": state.employment_type,
                "experience_required": state.experience_required,
                "salary_range": state.salary_range,
                "required_skills": state.required_skills,
                "nice_to_have_skills": state.nice_to_have_skills,
                "responsibilities": state.responsibilities,
                "qualifications": state.qualifications,
            }
        else:
            # resume — requires existing session with JD
            session_data = await redis_client.get_json(f"session:{session_id}")
            jd_context = {
                "required_skills": session_data.get("required_skills", []) if session_data else [],
                "nice_to_have_skills": session_data.get("nice_to_have_skills", []) if session_data else [],
            }
            resume_result = await parse_resume(output_path, jd_context)

            if session_data:
                session_data.update(
                    resume_file_path=output_path,
                    resume_raw_text=resume_result.get("raw_text", ""),
                    candidate_name=resume_result.get("candidate_name", "Candidate"),
                    candidate_email=resume_result.get("email", ""),
                    candidate_phone=resume_result.get("phone", ""),
                    current_role=resume_result.get("current_role", ""),
                    total_experience_years=resume_result.get("total_experience_years", 0),
                    candidate_skills=resume_result.get("skills", []),
                    experience=resume_result.get("experience", []),
                    education=resume_result.get("education", []),
                    match_score=resume_result.get("match_score", 0),
                    matched_skills=resume_result.get("matched_skills", []),
                    missing_skills=resume_result.get("missing_skills", []),
                )
                await redis_client.set_json(f"session:{session_id}", session_data)

            _score = resume_result.get("match_score", 0)
            result = {
                "session_id": session_id,
                "candidate_name": resume_result.get("candidate_name", "Candidate"),
                "candidate_email": resume_result.get("email", ""),
                "candidate_phone": resume_result.get("phone", ""),
                "current_role": resume_result.get("current_role", ""),
                "total_experience_years": resume_result.get("total_experience_years", 0),
                "candidate_skills": resume_result.get("skills", []),
                "match_score": _score,
                "match_tier": get_match_tier(_score),
                "matched_skills": resume_result.get("matched_skills", []),
                "missing_skills": resume_result.get("missing_skills", []),
            }

        # ── 4. Done ──────────────────────────────────────────────────
        upload_meta["status"] = "complete"
        upload_meta["result"] = result
        await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)

    except Exception as exc:
        logger.exception("Chunked upload processing failed for %s", upload_id)
        upload_meta["status"] = "error"
        upload_meta["error"] = str(exc)
        await redis_client.set(f"upload:{upload_id}", json.dumps(upload_meta), ex=3600)


# ── Step 1: Upload JD ───────────────────────────────────────────────

@router.post("/upload-jd")
async def upload_jd(
    jd_file: UploadFile = File(..., description="Job description PDF"),
) -> Dict[str, Any]:
    """Upload a JD PDF, parse it, and return extracted fields as a preview.

    Creates a new session in Redis with JD data so that the resume
    can be uploaded separately in a second step.
    """
    session_id = uuid.uuid4().hex
    jd_path = await _save_upload(jd_file, f"jd_{session_id}")

    try:
        jd_data = await parse_jd(jd_path)
    except Exception as exc:
        logger.exception("JD parsing failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"JD parsing failed: {exc}")

    # Persist partial state to Redis
    state = InterviewState(
        session_id=session_id,
        jd_file_path=jd_path,
        jd_raw_text=jd_data.get("raw_text", ""),
        job_title=jd_data.get("job_title", ""),
        company=jd_data.get("company", ""),
        location=jd_data.get("location", ""),
        employment_type=jd_data.get("employment_type", ""),
        experience_required=jd_data.get("experience_required", ""),
        salary_range=jd_data.get("salary_range", ""),
        required_skills=jd_data.get("required_skills", []),
        nice_to_have_skills=jd_data.get("nice_to_have_skills", []),
        responsibilities=jd_data.get("responsibilities", []),
        qualifications=jd_data.get("qualifications", []),
    )
    await redis_client.set_json(f"session:{session_id}", state.model_dump())

    return {
        "session_id": session_id,
        "job_title": state.job_title,
        "company": state.company,
        "location": state.location,
        "employment_type": state.employment_type,
        "experience_required": state.experience_required,
        "salary_range": state.salary_range,
        "required_skills": state.required_skills,
        "nice_to_have_skills": state.nice_to_have_skills,
        "responsibilities": state.responsibilities,
        "qualifications": state.qualifications,
    }


# ── Step 2: Upload Resume ───────────────────────────────────────────

@router.post("/upload-resume")
async def upload_resume(
    resume_file: UploadFile = File(..., description="Candidate resume PDF"),
    session_id: str = Form(..., description="Session ID from upload-jd step"),
    candidate_name: str = Form("Candidate"),
) -> Dict[str, Any]:
    """Upload a resume PDF against an existing session and return candidate preview.

    Parses the resume, computes match score against the JD already stored
    in the session, then runs the remaining setup pipeline (research + merge).
    """
    # Load existing session (must have JD already)
    session_data = await redis_client.get_json(f"session:{session_id}")
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found — upload JD first")

    resume_path = await _save_upload(resume_file, f"resume_{session_id}")

    # Parse resume with JD context for match scoring
    jd_data = {
        "required_skills": session_data.get("required_skills", []),
        "nice_to_have_skills": session_data.get("nice_to_have_skills", []),
    }
    try:
        resume_data = await parse_resume(resume_path, jd_data)
    except Exception as exc:
        logger.exception("Resume parsing failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {exc}")

    # Update session state with resume data
    session_data.update(
        resume_file_path=resume_path,
        resume_raw_text=resume_data.get("raw_text", ""),
        candidate_name=candidate_name or resume_data.get("candidate_name", "Candidate"),
        candidate_email=resume_data.get("email", ""),
        candidate_phone=resume_data.get("phone", ""),
        current_role=resume_data.get("current_role", ""),
        total_experience_years=resume_data.get("total_experience_years", 0),
        candidate_skills=resume_data.get("skills", []),
        experience=resume_data.get("experience", []),
        education=resume_data.get("education", []),
        match_score=resume_data.get("match_score", 0),
        matched_skills=resume_data.get("matched_skills", []),
        missing_skills=resume_data.get("missing_skills", []),
    )
    await redis_client.set_json(f"session:{session_id}", session_data)

    _s = session_data.get("match_score", 0)
    return {
        "session_id": session_id,
        "candidate_name": session_data["candidate_name"],
        "candidate_email": session_data.get("candidate_email", ""),
        "candidate_phone": session_data.get("candidate_phone", ""),
        "current_role": session_data.get("current_role", ""),
        "total_experience_years": session_data.get("total_experience_years", 0),
        "candidate_skills": session_data.get("candidate_skills", []),
        "match_score": _s,
        "match_tier": get_match_tier(_s),
        "matched_skills": session_data.get("matched_skills", []),
        "missing_skills": session_data.get("missing_skills", []),
    }


# ── Step 3: Generate interview link (runs research + merge) ─────────

@router.post("/prepare/{session_id}")
async def prepare_interview(session_id: str) -> Dict[str, Any]:
    """Run the setup pipeline (research + merge) and finalize the session.

    Call this after both JD and resume have been uploaded.
    Returns the interview link the recruiter can share with the applicant.
    """
    session_data = await redis_client.get_json(f"session:{session_id}")
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    state = InterviewState(**session_data)

    try:
        result_dict: Dict[str, Any] = await setup_graph.ainvoke(state.model_dump())
        state = InterviewState(**result_dict)
    except Exception as exc:
        logger.exception("Setup graph failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Setup pipeline failed: {exc}")

    await redis_client.set_json(f"session:{session_id}", state.model_dump())

    return {
        "session_id": session_id,
        "interview_ready": True,
        "job_title": state.job_title,
        "candidate_name": state.candidate_name,
        "match_score": state.match_score,
        "match_tier": get_match_tier(state.match_score),
        "max_questions": state.max_questions,
        "context_preview": (state.interview_context or "")[:400],
    }


# ── Read session ─────────────────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """Return the full session state stored in Redis."""
    data = await redis_client.get_json(f"session:{session_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data

