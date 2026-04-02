# ARIA Interview Engine — Module Contracts

## Architecture

ARIA uses a clean `InterviewEngine` class (no LangGraph, no LangChain).
Each candidate turn requires exactly **ONE LLM call** that evaluates the
answer AND generates ARIA's next spoken response.

## Module Contracts

### `backend/interview/state.py`

- **InterviewState** — Pydantic model holding all session data
- **ConversationTurn** — Role + content + timestamp
- **get_match_tier(score)** — Convert numeric score to tier label

### `backend/interview/engine.py` — InterviewEngine

| Method | Input | Output | LLM Calls |
|--------|-------|--------|-----------|
| `generate_greeting()` | — | `str` (greeting text) | 1 |
| `process_turn(text)` | candidate text | `TurnResult(aria_text, score_entry, should_end)` | 1 |
| `build_closing_questions()` | — | `list[str]` (logistics questions) | 0 |
| `extract_logistics()` | — | `dict` (structured logistics) | 1 |
| `generate_verdict()` | — | `dict` (full verdict) | 1 |
| `run_research()` | — | updates `state.research_context` | 0 (Tavily) |
| `build_interview_context()` | — | updates `state.interview_context` | 0 |
| `get_state_dict()` | — | `dict` (for Redis storage) | 0 |

### `backend/interview/prompts.py`

- **ARIA_SYSTEM** — System prompt with personality, rules, multilingual support
- **build_greeting_prompt(state)** — Opening greeting
- **build_turn_prompt(state, text, covered, uncovered, is_intro)** — Combined evaluate+respond
- **build_verdict_prompt(state, avg_score)** — Final evaluation

### `backend/llm/provider.py`

- **llm_invoke(messages)** — Multi-provider fallback chain via httpx
- **llm_invoke_json(messages)** — Same but requests JSON output
- Providers: Cerebras → Anthropic → Groq → Bedrock → Gemini → Ollama

### `backend/api/websocket.py`

- WebSocket at `/interview/{session_id}`
- Flow: greeting → intro → loop(audio → transcribe → process_turn → TTS) → closing → verdict
- Idle detection (60s check-in, 180s timeout)
- Reconnection support

## General Requirements

- Type hints required for all inputs/outputs
- Docstrings required for all functions
- async/await for all I/O
- No LangGraph, no LangChain
- State mutations only through the engine
