# Copilot Agent Instructions for ARIA: AI Interview System

## Project Context

**ARIA** is a voice-based AI pre-screening interviewer that:

- Accepts a Job Description (JD) PDF and candidate Resume PDF
- Parses PDFs using PyMuPDF with LLM-based structured extraction
- Optionally supplements context with Tavily web research
- Conducts a spoken pre-screening interview via WebSocket
- Uses faster-whisper (local, "small" model) for Speech-to-Text with Filipino language support
- Uses edge-tts (en-US-JennyNeural) for Text-to-Speech — free, no API key
- Uses a multi-provider LLM fallback chain (Cerebras → Anthropic → Groq → Bedrock → Gemini → Ollama), all called via httpx
- Stores session state in Redis (with in-memory fallback)

### Stack

- **Backend:** Python 3.12, FastAPI, PyMuPDF, httpx (direct LLM calls), faster-whisper, edge-tts
- **Frontend:** React 18 (functional components), Vite, Web Audio API, WebSockets
- **State:** Redis (Upstash) with in-memory fallback
- **LLM:** Multi-provider via httpx — primary: Cerebras Qwen 3 235B
- **No LangGraph. No LangChain.** — Plain Python + direct API calls.

### Architecture

```
backend/
  main.py              → FastAPI app, CORS, routers
  config.py            → Pydantic Settings (.env loader)
  redis_client.py      → Redis client with in-memory fallback
  interview/
    state.py           → InterviewState Pydantic model, ConversationTurn
    engine.py          → InterviewEngine class (greeting, process_turn, verdict)
    prompts.py         → ARIA personality + all prompt templates
  llm/
    provider.py        → Multi-provider LLM fallback (httpx, no SDKs)
  audio/
    stt.py             → Groq Whisper → faster-whisper fallback
    tts.py             → edge-tts
  api/
    recruiter.py       → Upload JD/resume, prepare interview, sessions
    applicant.py       → Pre-join info, join session, view results
    websocket.py       → Live interview WebSocket endpoint
  utils/
    pdf_parser.py      → PDF extraction + LLM-based structured parsing
    gender_detector.py → Filipino name-based gender/address detection
```

### Key Design Decisions

1. **ONE LLM call per turn** — `engine.process_turn(text)` evaluates the answer AND generates ARIA's next response in a single call. Replaces the old 3-call flow (evaluate → route → question).
2. **No LLM routing** — The decision to continue/end is pure Python logic in `_should_end()`: question_count >= max → end.
3. **Breadth via prompts** — Instead of domain clustering heuristics, the prompt tells the LLM: "You have N questions left and M uncovered skills. MOVE ON."
4. **max_questions = 8** — Pre-screening pace, not deep technical interview.

### Coding Standards

- **Python:**
  - PEP8 compliant
  - Type hints required everywhere
  - All I/O must use async/await
  - Docstrings required for all functions
- **React:**
  - Functional components only
  - Custom hooks for audio logic
  - No inline styles
- **Environment variables:**
  - Use `.env` files
  - Never hardcode secrets
- **Audio processing:**
  - Must be non-blocking

## Agent Instructions

- Always follow the coding standards above
- Never hardcode API keys or secrets
- Use async/await for all I/O
- All audio processing must be non-blocking
- Keep the interview engine simple — no over-engineering
- Write clear docstrings and comments for maintainability
- Ensure all PRs pass CI
