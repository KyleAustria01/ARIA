"""
ARIA Interview API — REST + Server-Sent Events (SSE)

Streamlined interview flow without WebSockets:
- POST /start → SSE stream with greeting
- POST /turn  → SSE stream with transcription, AI response, audio
- GET  /status → current interview state
"""

import asyncio
import base64
import json
import tempfile
import traceback
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from backend.audio.stt import transcribe
from backend.audio.tts import synthesize
from backend.config import settings
from backend.interview.engine import InterviewEngine
from backend.redis_client import redis_client

router = APIRouter(prefix="/api/interview", tags=["interview"])


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def sse_event(event: str, data: dict) -> str:
    """Format an SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def get_engine(session_id: str) -> InterviewEngine:
    """Load interview engine from Redis."""
    raw = await redis_client.get(f"session:{session_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Session not found")
    
    data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
    engine = InterviewEngine.from_dict(data.get("engine", data))
    return engine


async def save_engine(session_id: str, engine: InterviewEngine):
    """Save interview engine to Redis."""
    raw = await redis_client.get(f"session:{session_id}")
    if raw:
        data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
    else:
        data = {}
    
    data["engine"] = engine.to_dict()
    await redis_client.set(f"session:{session_id}", json.dumps(data))


# ─────────────────────────────────────────────────────────────────
# SSE Generators
# ─────────────────────────────────────────────────────────────────

async def stream_start(session_id: str) -> AsyncGenerator[str, None]:
    """Stream the interview start (greeting)."""
    try:
        engine = await get_engine(session_id)
        
        yield sse_event("phase", {"phase": "starting", "message": "Generating greeting..."})
        
        # Generate greeting
        greeting = await engine.generate_greeting()
        yield sse_event("response", {"text": greeting, "complete": True})
        
        # Generate TTS
        yield sse_event("phase", {"phase": "synthesizing", "message": "Generating audio..."})
        audio_bytes = await synthesize(greeting)
        audio_b64 = base64.b64encode(audio_bytes).decode() if audio_bytes else None
        
        if audio_b64:
            yield sse_event("audio", {"data": audio_b64, "format": "mp3"})
        
        # Save state
        await save_engine(session_id, engine)
        
        yield sse_event("phase", {"phase": "intro", "message": "Waiting for introduction"})
        yield sse_event("done", {"success": True})
        
    except Exception as e:
        traceback.print_exc()
        yield sse_event("error", {"message": str(e)})


async def stream_turn(
    session_id: str,
    user_text: str | None = None,
    audio_path: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a single interview turn."""
    try:
        engine = await get_engine(session_id)
        
        # Transcribe audio if provided
        transcript = user_text
        if audio_path and not transcript:
            yield sse_event("phase", {"phase": "transcribing", "message": "Processing audio..."})
            # Read audio file and transcribe
            audio_bytes = Path(audio_path).read_bytes()
            suffix = Path(audio_path).suffix or ".webm"
            transcript = await transcribe(audio_bytes, suffix)
            yield sse_event("transcription", {"text": transcript})
        
        if not transcript:
            yield sse_event("error", {"message": "No input received"})
            return
        
        # Check if interview is complete
        if engine.state.phase == "complete":
            yield sse_event("phase", {"phase": "complete", "message": "Interview already complete"})
            yield sse_event("done", {"success": True, "complete": True})
            return
        
        # Process turn
        yield sse_event("phase", {"phase": "thinking", "message": "Processing response..."})
        
        result = await engine.process_turn(transcript)
        aria_response = result.get("aria_response", "")
        
        # Stream response text
        yield sse_event("response", {
            "text": aria_response,
            "complete": True,
            "score": result.get("score"),
            "skill_area": result.get("skill_area"),
            "action": result.get("action"),
        })
        
        # Check for phase transitions
        current_phase = engine.state.phase
        if current_phase == "closing":
            yield sse_event("phase", {"phase": "closing", "message": "Moving to closing questions"})
        elif current_phase == "complete":
            yield sse_event("phase", {"phase": "complete", "message": "Interview complete"})
        
        # Generate TTS
        if aria_response and current_phase != "complete":
            yield sse_event("phase", {"phase": "synthesizing", "message": "Generating audio..."})
            audio_bytes = await synthesize(aria_response)
            audio_b64 = base64.b64encode(audio_bytes).decode() if audio_bytes else None
            
            if audio_b64:
                yield sse_event("audio", {"data": audio_b64, "format": "mp3"})
        
        # Save state
        await save_engine(session_id, engine)
        
        # Include verdict if complete
        if current_phase == "complete":
            verdict = engine.state.verdict
            yield sse_event("verdict", {
                "overall_verdict": verdict.get("overall_verdict", ""),
                "overall_score": verdict.get("overall_score", 0),
                "recommendation": verdict.get("recommendation", ""),
            })
        
        yield sse_event("done", {
            "success": True,
            "complete": current_phase == "complete",
            "question_count": engine.state.question_count,
            "max_questions": engine.state.max_questions,
        })
        
    except Exception as e:
        traceback.print_exc()
        yield sse_event("error", {"message": str(e)})
    finally:
        # Clean up temp audio file
        if audio_path:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except:
                pass


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.post("/{session_id}/start")
async def start_interview(session_id: str):
    """
    Start the interview and stream the greeting.
    
    Returns SSE stream with events:
    - phase: current phase
    - response: AI text response
    - audio: base64 encoded audio
    - done: stream complete
    """
    return StreamingResponse(
        stream_start(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/{session_id}/turn")
async def process_turn(
    session_id: str,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
):
    """
    Process a single interview turn.
    
    Send either:
    - audio: WebM/MP3/WAV audio file
    - text: Plain text input
    
    Returns SSE stream with events:
    - phase: current phase
    - transcription: transcribed audio (if audio sent)
    - response: AI text response
    - audio: base64 encoded audio
    - verdict: final verdict (if interview complete)
    - done: stream complete
    """
    audio_path = None
    
    # Save audio to temp file if provided
    if audio and audio.filename:
        suffix = Path(audio.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await audio.read()
            tmp.write(content)
            audio_path = tmp.name
    
    return StreamingResponse(
        stream_turn(session_id, user_text=text, audio_path=audio_path),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/status")
async def get_status(session_id: str):
    """Get current interview status."""
    engine = await get_engine(session_id)
    state = engine.state
    
    return {
        "session_id": session_id,
        "phase": state.phase,
        "question_count": state.question_count,
        "max_questions": state.max_questions,
        "is_complete": state.phase == "complete",
        "candidate_name": state.candidate_name,
        "job_title": state.job_title,
        "scores": state.scores,
        "verdict": state.verdict if state.phase == "complete" else None,
    }


@router.post("/{session_id}/text")
async def process_text_turn(session_id: str, text: str = Form(...)):
    """
    Simplified text-only turn endpoint.
    Same as /turn but only accepts text, no audio upload.
    """
    return StreamingResponse(
        stream_turn(session_id, user_text=text, audio_path=None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
