"""
FastAPI application entry point for ARIA MVP 2.0.

Registers all routers, configures CORS, and handles startup/shutdown.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import applicant, recruiter
from backend.api import websocket as ws_router
from backend.redis_client import redis_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Verify Redis connectivity on startup; log shutdown."""
    logger.info("ARIA backend starting up…")
    try:
        await redis_client.client.ping()
        logger.info("Redis connection OK.")
    except Exception as exc:
        logger.warning("Redis ping failed: %s — continuing anyway.", exc)
    yield
    logger.info("ARIA backend shutting down.")


app = FastAPI(
    title="ARIA Interview System",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS — allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(recruiter.router, prefix="/api/recruiter", tags=["recruiter"])
app.include_router(applicant.router, prefix="/api/applicant", tags=["applicant"])

# WebSocket router (no /api prefix — nginx routes /ws/* directly)
app.include_router(ws_router.router, prefix="/ws", tags=["websocket"])


@app.get("/api/health", tags=["health"])
async def health() -> dict:
    """Liveness check endpoint."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/tts-test", tags=["health"])
async def tts_test() -> dict:
    """Test TTS pipeline — synthesize a short phrase and return stats."""
    from backend.audio.tts import synthesize
    text = "Hello, this is a test."
    audio = await synthesize(text)
    return {
        "text": text,
        "audio_bytes": len(audio),
        "ok": len(audio) > 0,
        "first_bytes": list(audio[:4]) if audio else [],
    }

