
"""
Text-to-speech (TTS) utilities for ARIA AI Interview System.

ElevenLabs is the primary provider (natural voice).
Falls back to edge-tts (Microsoft Edge TTS, free, no API key) when
the ElevenLabs key is missing or the request fails.
"""

import io
import logging
from typing import Optional

import edge_tts
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# ── ElevenLabs constants ──────────────────────────────────────────────
_ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_ELEVENLABS_TIMEOUT = 30.0  # seconds


async def _elevenlabs_synthesize(text: str) -> Optional[bytes]:
    """Call ElevenLabs TTS API and return raw MPEG audio bytes.

    Returns None on any failure so the caller can fall back to edge-tts.
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
        logger.warning("ElevenLabs TTS failed, falling back to edge-tts: %s", exc)
        return None


# ── edge-tts fallback (free, no API key) ──────────────────────────────
# Uses the same TTS engine as Microsoft Edge Read Aloud.
_EDGE_VOICE = "en-US-JennyNeural"  # Natural female voice


async def _edge_tts_synthesize(text: str) -> bytes:
    """Render *text* to MP3 bytes using edge-tts (async, no key needed)."""
    communicate = edge_tts.Communicate(text, _EDGE_VOICE)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    audio_bytes = buffer.getvalue()
    logger.debug("edge-tts: %d chars → %d bytes", len(text), len(audio_bytes))
    return audio_bytes


# ── Public API ────────────────────────────────────────────────────────
async def synthesize(text: str) -> bytes:
    """Convert text to speech audio bytes (non-blocking).

    Tries ElevenLabs first; falls back to edge-tts on failure.
    Returns MP3 bytes from either provider.
    """
    if not text or not text.strip():
        return b""

    clean = text.strip()

    # Try ElevenLabs first
    audio = await _elevenlabs_synthesize(clean)
    if audio:
        logger.info("TTS via ElevenLabs: %d bytes for %d chars", len(audio), len(clean))
        return audio

    # Fallback to edge-tts (free, works on any server)
    logger.info("Trying edge-tts fallback for %d chars", len(clean))
    try:
        audio_bytes = await _edge_tts_synthesize(clean)
        if audio_bytes:
            logger.info("TTS via edge-tts: %d bytes for %d chars", len(audio_bytes), len(clean))
            return audio_bytes
    except Exception as exc:
        logger.error("edge-tts synthesis failed: %s", exc)

    logger.error("TTS synthesis failed entirely for: %s", clean[:50])
    return b""
