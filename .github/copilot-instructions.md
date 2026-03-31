# Copilot Agent Instructions for ARIA: AI Interview System

## Project Context

**ARIA** is a voice-based AI interviewer that:

- Accepts a Job Description (JD) PDF upload
- Parses the PDF using PyMuPDF
- Supplements the JD with web research via Tavily
- Conducts a spoken interview with an applicant using OpenAI Whisper (speech-to-text) and ElevenLabs (text-to-speech)
- Orchestrates the interview using LangGraph with stateful, typed, pure-function nodes
- Uses Anthropic Claude (claude-sonnet) as the LLM
- Stores state in Redis

### Stack

- **Backend:** Python 3.11+, FastAPI, LangGraph, LangChain, PyMuPDF, Tavily API, OpenAI Whisper, ElevenLabs TTS
- **Frontend:** React (functional components), Web Audio API, WebSockets
- **State:** Redis
- **LLM:** Anthropic Claude (claude-sonnet)

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
- **LangGraph nodes:**
  - Pure functions
  - Typed state
- **Environment variables:**
  - Use `.env` files
  - Never hardcode secrets
- **Audio processing:**
  - Must be non-blocking

### LangGraph Node Overview

1. **upload_jd_node** — Receives and stores uploaded PDF
2. **parse_pdf_node** — Extracts text using PyMuPDF
3. **research_node** — Tavily web search to supplement JD
4. **merge_context_node** — Combines PDF + research into interview context
5. **intro_node** — ARIA greets and opens the interview
6. **question_node** — Asks one question at a time based on context + history
7. **evaluate_answer_node** — Internally scores the answer
8. **router_node** — Decides: ask more OR finalize
9. **final_evaluation_node** — Produces structured verdict

## Agent Instructions

- Always follow the coding standards above
- Ensure all LangGraph nodes are pure, typed, and stateless except for explicit state transitions
- Never hardcode API keys or secrets
- Use async/await for all I/O (Python, React)

- All audio processing must be non-blocking

## Current Status

- All 48 files generated
- graph_builder.py added
- All imports verified
- All routes verified
- All placeholders removed
- App is ready to run
- Write clear docstrings and comments for maintainability
- Ensure all PRs pass CI (pytest for Python, vitest for React)
