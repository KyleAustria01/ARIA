"""
LangGraph node: question_node for ARIA AI Interview System.
Generates the next interview question based on context and history.
"""
from backend.langgraph.state import InterviewState
from langchain.llms import ChatAnthropic
from backend.config import settings

async def question_node(state: InterviewState) -> InterviewState:
    """
    Generates the next interview question using LLM and updates state.
    Args:
        state (InterviewState): Current LangGraph state with context and history.
    Returns:
        InterviewState: Updated state with new question in questions/history.
    """
    if not state.context:
        raise ValueError("context must be set in state.")
    llm = ChatAnthropic(model="claude-3-sonnet-20240229", api_key=settings.gemini_api_key)
    prompt = (
        f"Given the following job description and research, generate the next interview question.\n"
        f"Context:\n{state.context}\n"
        f"Previous questions: {state.questions}\n"
        f"Previous answers: {state.answers}\n"
        "Return only the question."
    )
    # LangChain LLM is synchronous, so run in executor
    import asyncio
    loop = asyncio.get_event_loop()
    def ask_llm(prompt: str) -> str:
        return llm(prompt)
    question = await loop.run_in_executor(None, ask_llm, prompt)
    state.questions.append(question)
    state.history.append({"type": "question", "message": question})
    return state
