"""
Speech-to-text (STT) utilities for ARIA AI Interview System.

Primary:  Groq Whisper API (whisper-large-v3-turbo) — fast, free tier.
Fallback: faster-whisper local (base model, CPU int8) — fully offline.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

import httpx
from faster_whisper import WhisperModel

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# faster-whisper lazy singleton
# ---------------------------------------------------------------------------

_whisper_model: Optional[WhisperModel] = None


def _get_whisper_model() -> WhisperModel:
    """Lazily load the faster-whisper model (base, CPU, int8)."""
    global _whisper_model
    if _whisper_model is None:
        logger.info("Loading faster-whisper base model (CPU int8)…")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


# ---------------------------------------------------------------------------
# Groq Whisper (primary)
# ---------------------------------------------------------------------------

_GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def _transcribe_groq(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """Send audio to Groq Whisper API and return transcript text."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _GROQ_STT_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": (f"audio{suffix}", audio_bytes, "audio/webm")},
            data={"model": "whisper-large-v3-turbo", "response_format": "json"},
        )
        response.raise_for_status()
        return response.json().get("text", "").strip()


# ---------------------------------------------------------------------------
# faster-whisper (fallback)
# ---------------------------------------------------------------------------


def _transcribe_local(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """Transcribe audio locally using faster-whisper (blocking)."""
    model = _get_whisper_model()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = model.transcribe(tmp_path, beam_size=5)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def transcribe(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """Transcribe speech audio bytes to text.

    Tries Groq Whisper first; falls back to local faster-whisper if Groq is
    unavailable or returns an error.

    Args:
        audio_bytes: Raw audio bytes (webm/wav/mp3 accepted).
        suffix: File extension hint for the temp file (e.g. '.webm', '.wav').

    Returns:
        Transcribed text string. Returns empty string if both paths fail.
    """
    if not audio_bytes:
        return ""

    # Primary: Groq Whisper
    if settings.groq_api_key:
        try:
            text = await _transcribe_groq(audio_bytes, suffix)
            if text:
                logger.debug("STT (Groq) success: %d chars", len(text))
                return text
        except Exception as exc:
            logger.warning("Groq STT failed (%s), falling back to local.", exc)

    # Fallback: faster-whisper local
    try:
        text = await asyncio.to_thread(_transcribe_local, audio_bytes, suffix)
        logger.debug("STT (local) success: %d chars", len(text))
        return text
    except Exception as exc:
        logger.error("Local STT failed: %s", exc)
        return ""
