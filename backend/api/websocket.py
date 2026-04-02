"""
WebSocket endpoint for ARIA — live interview orchestration.

Protocol
--------
Client → Server (binary):
    <raw audio bytes>          applicant's recorded answer (webm/wav)

Client → Server (text JSON):
    {"type": "ready"}          frontend finished playing ARIA audio
    {"type": "recording_started"}  applicant started recording
    {"type": "recording_stopped"}  applicant stopped recording

Server → Client (text JSON):
    {"type": "transcript", "role": "aria",      "text": "...", "question_count": N}
    {"type": "transcript", "role": "applicant", "text": "..."}
    {"type": "thinking"}                        ARIA is processing
    {"type": "verdict",    "data": {...}}        interview complete
    {"type": "error",      "message": "..."}
    {"type": "checkin",    "text": "..."}        idle check-in
    {"type": "timeout",    "text": "..."}        session timed out
    {"type": "resume",     ...}                  resuming previous session
    {"type": "resumed",    "text": "..."}        resume acknowledgment

Server → Client (binary):
    <MP3 audio bytes>          ARIA's spoken response
"""

import asyncio
import json
import logging
from time import time
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.audio.stt import transcribe
from backend.audio.tts import synthesize
from backend.config import settings
from backend.interview.engine import InterviewEngine, TurnResult
from backend.interview.state import InterviewState
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers (kept from original — these are solid)
# ---------------------------------------------------------------------------

async def _send_json(ws: WebSocket, payload: Dict[str, Any]) -> None:
    """Send a JSON text frame, swallowing errors if connection is gone."""
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:
        pass


async def _send_audio(ws: WebSocket, audio: bytes) -> None:
    """Send a binary audio frame, swallowing errors if connection is gone."""
    if audio:
        try:
            logger.info("Sending %d bytes of TTS audio to client", len(audio))
            await ws.send_bytes(audio)
        except Exception as exc:
            logger.warning("Failed to send audio bytes: %s", exc)
    else:
        logger.warning("_send_audio called with empty audio — TTS likely failed")


async def _send_debug(ws: WebSocket, engine: InterviewEngine) -> None:
    """Send debug state snapshot in development mode only."""
    if settings.app_env != "development":
        return
    s = engine.state
    await _send_json(ws, {
        "type": "debug",
        "state_summary": {
            "question_count": s.question_count,
            "max_questions": s.max_questions,
            "covered_skill_areas": s.covered_skill_areas,
            "scores": [
                {"score": sc.get("score"), "skill": sc.get("skill_area")}
                for sc in (s.scores or [])[-5:]
            ],
            "is_complete": s.is_complete,
        },
    })


async def _aria_speak(
    ws: WebSocket,
    text: str,
    role: str = "aria",
    question_count: int = 0,
) -> None:
    """Send transcript JSON then TTS audio for the given text."""
    payload: Dict[str, Any] = {"type": "transcript", "role": role, "text": text}
    if role == "aria":
        payload["question_count"] = question_count
    await _send_json(ws, payload)
    audio = await synthesize(text)
    await _send_audio(ws, audio)


async def _wait_for_audio(ws: WebSocket) -> bytes:
    """Wait for audio from the frontend.

    - Short 2-second polls for signal reactivity.
    - ``recording_started`` / ``ready`` reset the idle timer.
    - 60-second gentle check-in during genuine silence.
    - 3-minute hard timeout ends the session.
    """
    check_in_sent = False
    is_recording = False
    start_time = asyncio.get_event_loop().time()

    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
        except asyncio.TimeoutError:
            elapsed = asyncio.get_event_loop().time() - start_time

            if elapsed > 180 and not is_recording:
                await _send_json(ws, {
                    "type": "timeout",
                    "text": (
                        "The session has timed out due to inactivity. "
                        "Please contact the recruiter for a new interview link."
                    ),
                })
                raise WebSocketDisconnect(code=1000)

            if elapsed > 60 and not check_in_sent and not is_recording:
                check_in_sent = True
                checkin_text = (
                    "Are you still there? Take your time, "
                    "I am ready when you are."
                )
                await _send_json(ws, {"type": "checkin", "text": checkin_text})
                audio = await synthesize(checkin_text)
                await _send_audio(ws, audio)

            continue

        if msg.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(code=1000)

        # Binary frame — audio blob
        if msg.get("bytes"):
            return msg["bytes"]

        # Text frame — control signals
        if msg.get("text"):
            try:
                data = json.loads(msg["text"])
                msg_type = data.get("type", "")

                if msg_type == "ready":
                    start_time = asyncio.get_event_loop().time()
                    check_in_sent = False
                    is_recording = False

                elif msg_type == "recording_started":
                    start_time = asyncio.get_event_loop().time()
                    check_in_sent = False
                    is_recording = True

                elif msg_type == "recording_stopped":
                    is_recording = False

            except Exception:
                pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/interview/{session_id}")
async def interview_websocket(ws: WebSocket, session_id: str) -> None:
    """Drive the live interview for the given session_id.

    Flow:
        1. Load state from Redis
        2. ARIA greeting  (engine.generate_greeting)
        3. Candidate intro → engine.process_turn → first question
        4. Loop: audio → transcribe → engine.process_turn → TTS
        5. Closing logistics → verdict
    """
    await ws.accept()
    logger.info("WS accepted for session %s", session_id)

    try:
        # ── Load state ────────────────────────────────────────────
        raw = await redis_client.get_json(f"session:{session_id}")
        if not raw:
            await _send_json(ws, {
                "type": "error",
                "message": "Session not found",
            })
            await ws.close()
            return

        state = InterviewState(**raw)
        engine = InterviewEngine(state)

        if state.is_complete:
            await _send_json(ws, {
                "type": "error",
                "message": "Interview already completed",
            })
            await ws.close()
            return

        # ── Resume or Fresh Start ─────────────────────────────────
        is_resuming = (
            len(state.conversation_history) > 0
            and state.question_count > 0
        )

        if is_resuming:
            await _handle_resume(ws, engine, session_id)
        else:
            await _handle_fresh_start(ws, engine, session_id)

        # ── Main Interview Loop ───────────────────────────────────
        while not engine.state.is_complete:
            # Receive applicant audio
            try:
                audio_bytes = await _wait_for_audio(ws)
            except WebSocketDisconnect:
                break

            # Show thinking indicator immediately
            await _send_json(ws, {"type": "thinking"})

            # Transcribe
            applicant_text = await transcribe(audio_bytes, suffix=".webm")
            if not applicant_text:
                applicant_text = "[inaudible]"

            # Show applicant transcript immediately (before LLM call)
            await _send_json(ws, {
                "type": "transcript",
                "role": "applicant",
                "text": applicant_text,
            })

            # Process turn — ONE LLM call (evaluate + respond)
            result: TurnResult = await engine.process_turn(applicant_text)

            # Save state to Redis
            await redis_client.set_json(
                f"session:{session_id}",
                engine.get_state_dict(),
            )
            await _send_debug(ws, engine)

            if result.should_end:
                # ── Closing phase ─────────────────────────────────
                await _handle_closing(ws, engine, session_id)
                break
            else:
                # Send ARIA's next question as audio
                await _aria_speak(
                    ws,
                    result.aria_text,
                    question_count=engine.state.question_count,
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected from session %s", session_id)
    except Exception as exc:
        logger.exception("Unhandled error in session %s", session_id)
        await _send_json(ws, {"type": "error", "message": str(exc)})
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sub-flows (extracted for readability)
# ---------------------------------------------------------------------------

async def _handle_fresh_start(
    ws: WebSocket,
    engine: InterviewEngine,
    session_id: str,
) -> None:
    """Handle a fresh interview — greeting, wait for intro, first question."""
    # ARIA greeting
    greeting = await engine.generate_greeting()
    await redis_client.set_json(
        f"session:{session_id}",
        engine.get_state_dict(),
    )
    await _aria_speak(ws, greeting, question_count=0)

    # Wait for candidate's intro / readiness audio
    try:
        ready_audio = await _wait_for_audio(ws)
    except WebSocketDisconnect:
        raise

    ready_text = ""
    if ready_audio:
        ready_text = await transcribe(ready_audio, suffix=".webm") or ""
        if ready_text:
            await _send_json(ws, {
                "type": "transcript",
                "role": "applicant",
                "text": ready_text,
            })

    if not ready_text:
        ready_text = "Hello"

    # Process intro → engine generates first question (ONE LLM call)
    await _send_json(ws, {"type": "thinking"})
    result: TurnResult = await engine.process_turn(ready_text)
    await redis_client.set_json(
        f"session:{session_id}",
        engine.get_state_dict(),
    )
    await _send_debug(ws, engine)

    # Send the first question
    await _aria_speak(
        ws,
        result.aria_text,
        question_count=engine.state.question_count,
    )


async def _handle_resume(
    ws: WebSocket,
    engine: InterviewEngine,
    session_id: str,
) -> None:
    """Handle reconnection — send history, repeat or generate next question."""
    state = engine.state
    addr = state.candidate_address or (
        state.candidate_name or "there"
    ).split()[0]

    logger.info(
        "Resuming session %s (Q%d)",
        session_id,
        state.question_count,
    )

    # Send history to frontend
    await _send_json(ws, {
        "type": "resume",
        "question_count": state.question_count,
        "conversation_history": [
            {"role": t.role, "text": t.content}
            for t in state.conversation_history
        ],
    })

    # Find last ARIA text
    last_aria_text = engine._last_aria_text()
    last_role = (
        state.conversation_history[-1].role
        if state.conversation_history
        else None
    )

    if last_role == "aria" and last_aria_text:
        # ARIA was waiting for a response — repeat last question
        resume_msg = f"Welcome back, {addr}! Let me repeat my last question. "
        await _send_json(ws, {"type": "resumed", "text": resume_msg})
        await _aria_speak(
            ws,
            resume_msg + last_aria_text,
            question_count=state.question_count,
        )
    else:
        # Last turn was applicant — generate next question
        resume_msg = f"Welcome back, {addr}! Let's continue where we left off."
        await _send_json(ws, {"type": "resumed", "text": resume_msg})
        await _aria_speak(ws, resume_msg, question_count=state.question_count)

        # Generate the next question
        last_answer = ""
        for t in reversed(state.conversation_history):
            if t.role == "applicant":
                last_answer = t.content
                break

        if last_answer:
            await _send_json(ws, {"type": "thinking"})
            result = await engine.process_turn(last_answer)
            await redis_client.set_json(
                f"session:{session_id}",
                engine.get_state_dict(),
            )
            await _aria_speak(
                ws,
                result.aria_text,
                question_count=engine.state.question_count,
            )


async def _handle_closing(
    ws: WebSocket,
    engine: InterviewEngine,
    session_id: str,
) -> None:
    """Handle closing logistics questions, verdict, and farewell."""
    state = engine.state

    # ── Logistics questions ───────────────────────────────────────
    logistics_qs = engine.build_closing_questions()
    logistics_raw: list[dict[str, str]] = []

    for lq in logistics_qs:
        await _aria_speak(
            ws,
            lq,
            question_count=state.question_count,
        )

        # Wait for candidate's answer
        try:
            lq_audio = await _wait_for_audio(ws)
        except WebSocketDisconnect:
            lq_audio = b""

        lq_answer = ""
        if lq_audio:
            await _send_json(ws, {"type": "thinking"})
            lq_answer = await transcribe(lq_audio, suffix=".webm") or ""
            if lq_answer:
                await _send_json(ws, {
                    "type": "transcript",
                    "role": "applicant",
                    "text": lq_answer,
                })

        logistics_raw.append({"question": lq, "answer": lq_answer})

    # Store raw logistics and extract structured fields
    engine.state.logistics_raw = logistics_raw
    await engine.extract_logistics()

    # ── Final verdict ─────────────────────────────────────────────
    await _send_json(ws, {"type": "thinking"})
    verdict = await engine.generate_verdict()

    # Save final state
    await redis_client.set_json(
        f"session:{session_id}",
        engine.get_state_dict(),
    )

    # ── Farewell ──────────────────────────────────────────────────
    candidate_first = (state.candidate_name or "").split()[0] or "there"
    closing = (
        f"That wraps up our conversation, {candidate_first}! "
        f"I really enjoyed learning about your experience. "
        f"The recruiting team will review everything and be in touch soon. "
        f"Thanks so much for your time — best of luck!"
    )
    await _aria_speak(ws, closing, question_count=state.question_count)

    # Send structured verdict
    await _send_json(ws, {"type": "verdict", "data": verdict})
