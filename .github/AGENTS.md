# LangGraph Node Contracts & Responsibilities — ARIA

## Node Contracts

All nodes must be **pure functions** with **typed state**. Each node receives the current state and returns the next state. No side effects except for explicit I/O nodes (e.g., upload, TTS, STT).

### 1. upload_jd_node

- **Input:** File upload (PDF)
- **Output:** File reference/path in state
- **Contract:** Accepts PDF, stores securely, returns reference

### 2. parse_pdf_node

- **Input:** File reference
- **Output:** Extracted text
- **Contract:** Uses PyMuPDF to extract all text from PDF

### 3. research_node

- **Input:** Extracted JD text
- **Output:** Supplementary research (string)
- **Contract:** Uses Tavily API to fetch relevant web context

### 4. merge_context_node

- **Input:** JD text + research
- **Output:** Combined interview context
- **Contract:** Merges and deduplicates context for interview

### 5. intro_node

- **Input:** Interview context
- **Output:** Greeting message (string)
- **Contract:** Generates ARIA's spoken greeting

### 6. question_node

- **Input:** Interview context + history
- **Output:** Next question (string)
- **Contract:** Generates one question at a time, context-aware

### 7. evaluate_answer_node

- **Input:** Question + answer
- **Output:** Score/feedback (structured)
- **Contract:** Scores answer using LLM, returns feedback

### 8. router_node

- **Input:** Interview state
- **Output:** Next node decision
- **Contract:** Decides whether to continue or finalize

### 9. final_evaluation_node

- **Input:** All answers + scores
- **Output:** Structured verdict (JSON)
- **Contract:** Produces final evaluation and summary

## General Requirements

- All nodes must be pure, stateless (except for explicit state transitions)
- Type hints required for all inputs/outputs
- Docstrings required for all node functions
- No direct I/O except for designated nodes
