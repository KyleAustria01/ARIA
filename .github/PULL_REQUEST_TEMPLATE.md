# Pull Request Checklist — ARIA: AI Interview System

## General

- [ ] PR title is descriptive
- [ ] Linked to relevant issue(s)
- [ ] No hardcoded secrets or API keys
- [ ] All environment variables documented in `.env.example`
- [ ] Code is well-commented and documented

## Backend (Python)

- [ ] PEP8 compliant
- [ ] All functions have type hints
- [ ] All I/O is async/await
- [ ] All functions have docstrings
- [ ] LangGraph nodes are pure functions with typed state
- [ ] Tests added/updated (pytest)

## Frontend (React)

- [ ] Functional components only
- [ ] Custom hooks for audio logic
- [ ] No inline styles
- [ ] All audio processing is non-blocking
- [ ] Tests added/updated (vitest)

## CI

- [ ] CI passes for both Python (pytest) and React (vitest)
