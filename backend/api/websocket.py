"""
WebSocket endpoint for ARIA MVP 2.0 — live interview orchestration.

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
from backend.interview_graph.closing_questions_node import (
    _build_logistics_questions,
    extract_logistics,
)
from backend.interview_graph.evaluate_answer_node import evaluate_answer_node
from backend.interview_graph.final_evaluation_node import final_evaluation_node
from backend.interview_graph.intro_node import intro_node
from backend.interview_graph.question_node import question_node
from backend.interview_graph.router_node import router_node
from backend.interview_graph.state import ConversationTurn, InterviewState
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply(state: InterviewState, updates: Dict[str, Any]) -> InterviewState:
    """Merge a node's partial-update dict back into the state."""
    if isinstance(updates, InterviewState):
        return updates
    if isinstance(updates, dict):
        return state.model_copy(update=updates)
    return state


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


async def _send_debug(ws: WebSocket, state: "InterviewState", node_name: str) -> None:
    """Send debug state snapshot in development mode only."""
    if settings.app_env != "development":
        return
    await _send_json(ws, {
        "type": "debug",
        "node": node_name,
        "state_summary": {
            "question_count": state.question_count,
            "is_nervous": state.candidate_nervous,
            "consecutive_nervous": state.consecutive_nervous_count,
            "non_answer_count": state.non_answer_count,
            "elaborate_requested": state.elaborate_requested,
            "scores": [
                {"score": s.get("score"), "skill": s.get("skill_area"), "hint": s.get("follow_up_hint")}
                for s in (state.scores or [])[-5:]
            ],
            "is_complete": state.is_complete,
        },
    })


async def _aria_speak(ws: WebSocket, text: str, role: str = "aria", question_count: int = 0) -> None:
    """Send transcript JSON then TTS audio for the given text."""
    payload: Dict[str, Any] = {"type": "transcript", "role": role, "text": text}
    if role == "aria":
        payload["question_count"] = question_count
    await _send_json(ws, payload)
    audio = await synthesize(text)
    await _send_audio(ws, audio)


async def _wait_for_audio(ws: WebSocket) -> bytes:
    """Wait for audio from the frontend.

    The frontend controls when recording stops — the backend never
    enforces a hard audio-receive timeout that could cut the applicant
    off mid-sentence.  Instead:

    - Short 2-second polls are used so we can react to signals quickly.
    - ``recording_started`` / ``ready`` signals reset the idle timer so
      the check-in is never fired while the applicant is speaking.
    - ``recording_stopped`` is a heads-up that the audio blob is on its
      way; we simply continue waiting for it.
    - A gentle 60-second check-in plays only during genuine silence.
    - The session ends only after 3 full minutes of uninterrupted silence.

    Returns audio bytes, or raises WebSocketDisconnect.
    """
    check_in_sent = False
    is_recording = False
    start_time = asyncio.get_event_loop().time()

    while True:
        try:
            # Short poll so we can evaluate signals promptly
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
        except asyncio.TimeoutError:
            elapsed = asyncio.get_event_loop().time() - start_time

            # End session after 3 minutes of silence (not while recording)
            if elapsed > 180 and not is_recording:
                await _send_json(ws, {
                    "type": "timeout",
                    "text": (
                        "The session has timed out due to inactivity. "
                        "Please contact the recruiter for a new interview link."
                    ),
                })
                raise WebSocketDisconnect(code=1000)

            # Check-in after 60 s of silence — only when NOT recording
            if elapsed > 60 and not check_in_sent and not is_recording:
                check_in_sent = True
                checkin_text = "Are you still there? Take your time, I am ready when you are."
                await _send_json(ws, {"type": "checkin", "text": checkin_text})
                audio = await synthesize(checkin_text)
                await _send_audio(ws, audio)

            continue

        if msg.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(code=1000)

        # ── Binary frame ── audio blob from applicant, return immediately
        if msg.get("bytes"):
            return msg["bytes"]

        # ── Text frame ── control signals from frontend
        if msg.get("text"):
            try:
                data = json.loads(msg["text"])
                msg_type = data.get("type", "")

                if msg_type == "ready":
                    # Frontend finished playing ARIA audio; reset idle clock
                    start_time = asyncio.get_event_loop().time()
                    check_in_sent = False
                    is_recording = False

                elif msg_type == "recording_started":
                    # Applicant is actively speaking; never send check-in now
                    start_time = asyncio.get_event_loop().time()
                    check_in_sent = False
                    is_recording = True

                elif msg_type == "recording_stopped":
                    # Audio blob is about to arrive; keep waiting
                    is_recording = False

            except Exception:
                pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/interview/{session_id}")
async def interview_websocket(ws: WebSocket, session_id: str) -> None:
    """Drive the live interview for the given session_id.

    Loads state from Redis, orchestrates node calls per turn, streams
    TTS audio and transcript events back to the client.
    """
    await ws.accept()
    logger.info("WS accepted for session %s", session_id)

    try:
        # ── Load state ────────────────────────────────────────────────────
        raw = await redis_client.get_json(f"session:{session_id}")
        if not raw:
            await _send_json(ws, {"type": "error", "message": "Session not found"})
            await ws.close()
            return

        state = InterviewState(**raw)

        if state.is_complete:
            await _send_json(ws, {"type": "error", "message": "Interview already completed"})
            await ws.close()
            return

        # ── Auto-start: no start signal needed ────────────────────────

        # ── Check if resuming an existing interview ───────────────────────
        is_resuming = len(state.conversation_history) > 0 and state.question_count > 0
        skip_question_node = False

        if is_resuming:
            # Real reconnect — WebSocket just opened with existing state in Redis
            logger.info("Resuming interview for session %s (Q%d)", session_id, state.question_count)
            candidate_addr = state.candidate_address or (state.candidate_name or "there").split()[0]

            await _send_json(ws, {
                "type": "resume",
                "question_count": state.question_count,
                "conversation_history": [
                    {"role": turn.role, "text": turn.content}
                    for turn in state.conversation_history
                ],
            })
            await _send_debug(ws, state, "resume")

            # Find the last ARIA question
            last_aria_text = None
            for turn in reversed(state.conversation_history):
                if turn.role == "aria":
                    last_aria_text = turn.content
                    break

            last_turn_role = state.conversation_history[-1].role if state.conversation_history else None

            if last_turn_role == "aria" and last_aria_text:
                # ARIA was waiting for a response — repeat the last question
                resume_msg = f"Welcome back, {candidate_addr}! Let me repeat my last question. "
                await _send_json(ws, {"type": "resumed", "text": resume_msg})
                await _aria_speak(ws, resume_msg + last_aria_text, question_count=state.question_count)
                # Question already sent — skip question_node on first loop iteration
                skip_question_node = True
            else:
                # Applicant had answered — generate next question
                resume_msg = f"Welcome back, {candidate_addr}! Let us continue where we left off."
                await _send_json(ws, {"type": "resumed", "text": resume_msg})
                await _aria_speak(ws, resume_msg, question_count=state.question_count)

                await _send_json(ws, {"type": "thinking"})
                updates = await question_node(state)
                state = _apply(state, updates)
                await redis_client.set_json(f"session:{session_id}", state.model_dump())
                await _send_debug(ws, state, "question_node")

                next_question = state.conversation_history[-1].content if state.conversation_history else "Please continue."
                await _aria_speak(ws, next_question, question_count=state.question_count)
                # Question already sent — skip question_node on first loop iteration
                skip_question_node = True

        else:
            # ── Fresh start: ARIA introduction ────────────────────────────
            updates = await intro_node(state)
            state = _apply(state, updates)
            await redis_client.set_json(f"session:{session_id}", state.model_dump())
            await _send_debug(ws, state, "intro_node")

            greeting = state.conversation_history[-1].content if state.conversation_history else "Hello! I'm ARIA, your AI interviewer. Let me know when you're ready."
            await _aria_speak(ws, greeting, question_count=0)

            # ── Wait for candidate to confirm readiness ───────────────────
            # Accept either audio (transcribed) or another "start" signal
            try:
                ready_audio = await _wait_for_audio(ws)
            except WebSocketDisconnect:
                return

            if ready_audio:
                ready_text = await transcribe(ready_audio, suffix=".webm")
                if ready_text:
                    state.conversation_history.append(
                        ConversationTurn(role="applicant", content=ready_text, timestamp=time())
                    )
                    await _send_json(ws, {"type": "transcript", "role": "applicant", "text": ready_text})

            # ── First question ────────────────────────────────────────────
            await _send_json(ws, {"type": "thinking"})
            updates = await question_node(state)
            state = _apply(state, updates)
            await redis_client.set_json(f"session:{session_id}", state.model_dump())
            await _send_debug(ws, state, "question_node")

            first_question = state.conversation_history[-1].content if state.conversation_history else "Tell me about yourself."
            await _aria_speak(ws, first_question, question_count=state.question_count)

        # ── Interview loop ────────────────────────────────────────────────
        while not state.is_complete:
            # Receive applicant audio
            try:
                audio_bytes = await _wait_for_audio(ws)
            except WebSocketDisconnect:
                break

            # Notify client that processing is starting
            await _send_json(ws, {"type": "thinking"})

            # STT — transcribe applicant's audio
            applicant_text = await transcribe(audio_bytes, suffix=".webm")
            if not applicant_text:
                applicant_text = "[inaudible]"

            # Append applicant turn to history
            state.conversation_history.append(
                ConversationTurn(role="applicant", content=applicant_text, timestamp=time())
            )
            await _send_json(ws, {"type": "transcript", "role": "applicant", "text": applicant_text})

            # Evaluate the answer
            updates = await evaluate_answer_node(state)
            state = _apply(state, updates)
            await _send_debug(ws, state, "evaluate_answer_node")

            # Route: continue or finalize
            updates = await router_node(state)
            state = _apply(state, updates)
            await _send_debug(ws, state, "router_node")

            if state.is_complete:
                # ── Closing logistics questions ───────────────────────────
                logistics_qs = _build_logistics_questions(state)
                logistics_raw: list[dict[str, str]] = []

                for lq in logistics_qs:
                    # ARIA asks the logistics question
                    state.conversation_history.append(
                        ConversationTurn(role="aria", content=lq, timestamp=time())
                    )
                    await _aria_speak(ws, lq, question_count=state.question_count)

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
                            state.conversation_history.append(
                                ConversationTurn(
                                    role="applicant",
                                    content=lq_answer,
                                    timestamp=time(),
                                )
                            )
                            await _send_json(
                                ws,
                                {"type": "transcript", "role": "applicant", "text": lq_answer},
                            )

                    logistics_raw.append({"question": lq, "answer": lq_answer})

                # Store raw logistics and extract structured fields
                state = _apply(state, {"logistics_raw": logistics_raw})
                updates = await extract_logistics(state)
                state = _apply(state, updates)

                # ── Final evaluation ──────────────────────────────────────
                await _send_json(ws, {"type": "thinking"})
                state = _apply(state, {"interview_ended_at": time()})
                updates = await final_evaluation_node(state)
                state = _apply(state, updates)
                await redis_client.set_json(f"session:{session_id}", state.model_dump())
                await _send_debug(ws, state, "final_evaluation_node")

                # Natural closing — reference the candidate by name
                candidate_first = (state.candidate_name or "").split()[0] or "there"
                closing = (
                    f"That wraps up our conversation, {candidate_first}! "
                    f"I really enjoyed learning about your experience. "
                    f"The recruiting team will review everything and be in touch soon. "
                    f"Thanks so much for your time — best of luck!"
                )
                await _aria_speak(ws, closing, question_count=state.question_count)

                # Send structured verdict
                verdict = state.verdict or {}
                await _send_json(ws, {"type": "verdict", "data": verdict})
                break

            else:
                # ── Next question ─────────────────────────────────────────
                # Skip question_node on first iteration after resume
                # (question was already sent above)
                if skip_question_node:
                    skip_question_node = False
                else:
                    updates = await question_node(state)
                    state = _apply(state, updates)
                    await redis_client.set_json(f"session:{session_id}", state.model_dump())
                    await _send_debug(ws, state, "question_node")

                    next_question = state.conversation_history[-1].content if state.conversation_history else "Please continue."
                    await _aria_speak(ws, next_question, question_count=state.question_count)

    except WebSocketDisconnect:
        logger.info("Client disconnected from session %s", session_id)
    except Exception as exc:
        logger.exception("Unhandled error in session %s", session_id)
        await _send_json(ws, {"type": "error", "message": str(exc)})
        try:
            await ws.close()
        except Exception:
            pass
