"""
LLM provider with automatic fallback chain.

Fallback order:
1. Cerebras (llama-3.3-70b) — fastest free (~0.3s)
2. Groq (llama-3.1-8b-instant) — fast free (~0.5s)
3. AWS Bedrock (Amazon Nova Lite) — paid but highly reliable
4. Gemini 2.0 Flash — free tier (~1-2s)
5. Ollama LLaMA 3.2 — local, offline (slow)

Each provider is tried in order. On failure or rate limit,
the next provider is attempted. If all fail, raises an exception.
"""
import json
import logging
from typing import Any

import httpx

from backend.config import settings

# AWS Bedrock is an optional dependency — only imported if boto3 is installed
try:
    import boto3  # type: ignore
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)

CEREBRAS_MODEL = "llama-3.3-70b"
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"
OLLAMA_MODEL = "llama3.2"

TIMEOUT = httpx.Timeout(90.0, connect=15.0)
MAX_TOKENS = 1024
TEMPERATURE = 0.4


class LLMProviderError(Exception):
    """Raised when all LLM providers fail."""


async def _call_cerebras(messages: list[dict[str, str]]) -> str:
    """Call Cerebras API (OpenAI-compatible) with the given messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.cerebras_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": CEREBRAS_MODEL,
                "messages": messages,
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_groq(messages: list[dict[str, str]]) -> str:
    """Call Groq API with the given messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_bedrock(messages: list[dict[str, str]]) -> str:
    """Call AWS Bedrock (Amazon Nova Lite) using the Converse API.

    Credentials are read exclusively from ``settings`` (injected from .env).
    Never hardcoded.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text.

    Raises:
        Exception: On AWS errors or missing credentials.
    """
    if not _BOTO3_AVAILABLE:
        raise RuntimeError("boto3 is not installed — run: pip install boto3")

    if not (settings.aws_access_key_id and settings.aws_secret_access_key):
        raise RuntimeError("AWS credentials not configured")

    # Build Bedrock Converse API payload
    # System messages are separated from the conversation turns
    system_parts: list[dict] = []
    converse_messages: list[dict] = []

    for msg in messages:
        if msg["role"] == "system":
            system_parts.append({"text": msg["content"]})
        else:
            bedrock_role = "user" if msg["role"] == "user" else "assistant"
            converse_messages.append({
                "role": bedrock_role,
                "content": [{"text": msg["content"]}],
            })

    # boto3 calls are synchronous — run in a thread to avoid blocking the event loop
    import asyncio
    import functools

    def _sync_call() -> str:
        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        kwargs: dict = {
            "modelId": settings.aws_bedrock_model_id,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
            },
        }
        if system_parts:
            kwargs["system"] = system_parts

        response = client.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(_sync_call))


async def _call_gemini(messages: list[dict[str, str]]) -> str:
    """Call Google Gemini API with the given messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = "user" if msg["role"] in ("user", "system") else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}],
        })

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": settings.gemini_api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": contents,
                "generationConfig": {
                    "temperature": TEMPERATURE,
                    "maxOutputTokens": MAX_TOKENS,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_ollama(messages: list[dict[str, str]]) -> str:
    """Call local Ollama instance with the given messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": TEMPERATURE,
                    "num_predict": MAX_TOKENS,
                    "num_ctx": 512,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


async def llm_invoke(messages: list[dict[str, str]]) -> str:
    """Invoke LLM with automatic fallback across providers.

    Tries Groq → Gemini → Ollama in order. Skips providers
    whose API keys are not configured.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        The assistant's response text from the first successful provider.

    Raises:
        LLMProviderError: If all providers fail.
    """
    providers: list[tuple[str, bool, Any]] = [
        ("cerebras", bool(settings.cerebras_api_key), _call_cerebras),
        ("groq", bool(settings.groq_api_key), _call_groq),
        ("bedrock", bool(settings.aws_access_key_id and settings.aws_secret_access_key), _call_bedrock),
        ("gemini", bool(settings.gemini_api_key), _call_gemini),
        ("ollama", True, _call_ollama),
    ]

    errors: list[str] = []

    for name, available, call_fn in providers:
        if not available:
            logger.debug("Skipping %s — no API key configured", name)
            continue
        try:
            result = await call_fn(messages)
            if result and result.strip():
                logger.info("LLM response from %s (%d chars)", name, len(result))
                return result.strip()
            logger.warning("%s returned empty response, trying next", name)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.warning("%s HTTP %d: %s", name, status, str(e)[:200])
            errors.append(f"{name}: HTTP {status}")
        except httpx.ConnectError:
            logger.warning("%s connection failed", name)
            errors.append(f"{name}: connection failed")
        except Exception as e:
            logger.warning("%s failed: %s", name, str(e)[:200])
            errors.append(f"{name}: {str(e)[:100]}")

    raise LLMProviderError(
        f"All LLM providers failed: {'; '.join(errors) or 'none configured'}"
    )


async def llm_invoke_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Invoke LLM and parse the response as JSON.

    Appends an instruction to return valid JSON. Strips markdown
    code fences if present before parsing.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        Parsed JSON dict from the LLM response.

    Raises:
        LLMProviderError: If all providers fail.
        json.JSONDecodeError: If the response is not valid JSON.
    """
    messages = messages.copy()
    if messages:
        messages[-1] = {
            **messages[-1],
            "content": messages[-1]["content"]
            + "\n\nRespond with valid JSON only. No markdown, no explanation.",
        }

    raw = await llm_invoke(messages)

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # remove closing fence
        cleaned = "\n".join(lines).strip()

    return json.loads(cleaned)
