
"""
Text-to-speech (TTS) utilities for ARIA AI Interview System.

ElevenLabs is the primary provider (natural voice).
Falls back to pyttsx3 (offline, robotic) when the API key is missing
or if the ElevenLabs request fails.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

import httpx
import pyttsx3

from backend.config import settings

logger = logging.getLogger(__name__)

# ── ElevenLabs constants ──────────────────────────────────────────────
_ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_ELEVENLABS_TIMEOUT = 30.0  # seconds


async def _elevenlabs_synthesize(text: str) -> Optional[bytes]:
    """Call ElevenLabs TTS API and return raw MPEG audio bytes.

    Returns None on any failure so the caller can fall back to pyttsx3.
    """
    api_key = settings.elevenlabs_api_key
    voice_id = settings.elevenlabs_voice_id
    if not api_key:
        return None

    url = _ELEVENLABS_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.80,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=_ELEVENLABS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            audio = resp.content
            logger.debug(
                "ElevenLabs TTS: %d chars → %d bytes", len(text), len(audio)
            )
            return audio
    except Exception as exc:
        logger.warning("ElevenLabs TTS failed, falling back to pyttsx3: %s", exc)
        return None


# ── pyttsx3 offline fallback ──────────────────────────────────────────
def _pyttsx3_synthesize(text: str) -> bytes:
    """Render *text* to WAV bytes using pyttsx3 (blocking).

    Initialises a fresh engine per call to avoid multi-thread issues.
    """
    engine = pyttsx3.init()
    tmp_path: str = ""
    try:
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)

        voices = engine.getProperty("voices") or []
        for voice in voices:
            name_lower = (voice.name or "").lower()
            if "zira" in name_lower or "female" in name_lower:
                engine.setProperty("voice", voice.id)
                break

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = tmp.name

        engine.save_to_file(text, tmp_path)
        engine.runAndWait()

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            engine.stop()
        except Exception:
            pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Public API ────────────────────────────────────────────────────────
async def synthesize(text: str) -> bytes:
    """Convert text to speech audio bytes (non-blocking).

    Tries ElevenLabs first; falls back to pyttsx3 on failure.
    Returns MP3 bytes from ElevenLabs or WAV bytes from pyttsx3.
    """
    if not text or not text.strip():
        return b""

    clean = text.strip()

    # Try ElevenLabs first
    audio = await _elevenlabs_synthesize(clean)
    if audio:
        return audio

    # Fallback to pyttsx3
    try:
        audio_bytes = await asyncio.to_thread(_pyttsx3_synthesize, clean)
        logger.debug("pyttsx3 TTS: %d chars → %d bytes", len(clean), len(audio_bytes))
        return audio_bytes
    except Exception as exc:
        logger.error("TTS synthesis failed entirely: %s", exc)
        return b""
