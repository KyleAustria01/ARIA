
"""
Text-to-speech (TTS) utilities for ARIA AI Interview System.

Uses edge-tts (Microsoft Edge TTS) — free, async, no API key needed.
Voice: en-US-JennyNeural (natural female voice).
"""

import io
import logging

import edge_tts

logger = logging.getLogger(__name__)

_EDGE_VOICE = "en-US-JennyNeural"


async def synthesize(text: str) -> bytes:
    """Convert text to speech audio bytes using edge-tts (non-blocking).

    Returns MP3 bytes or empty bytes on failure.
    """
    if not text or not text.strip():
        return b""

    clean = text.strip()

    try:
        communicate = edge_tts.Communicate(clean, _EDGE_VOICE)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        audio_bytes = buffer.getvalue()
        logger.info("edge-tts: %d chars → %d bytes", len(clean), len(audio_bytes))
        return audio_bytes
    except Exception as exc:
        logger.error("edge-tts synthesis failed: %s", exc)
        return b""
