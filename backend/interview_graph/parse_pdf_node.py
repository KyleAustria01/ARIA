"""
LangGraph node: parse_pdf_node for ARIA AI Interview System.
Extracts text from PDF using PyMuPDF and updates state.
"""
from typing import Any
from interview_graph.state import InterviewState
import fitz  # PyMuPDF

async def parse_pdf_node(state: InterviewState) -> InterviewState:
    """
    Extracts text from the uploaded PDF using PyMuPDF and updates state.
    Args:
        state (InterviewState): Current LangGraph state with file_path set.
    Returns:
        InterviewState: Updated state with jd_text set.
    """
    if not state.file_path:
        raise ValueError("No file_path set in state.")
    text = ""
    # PyMuPDF is synchronous, so run in thread executor
    import asyncio
    loop = asyncio.get_event_loop()
    def extract_text(path: str) -> str:
        doc = fitz.open(path)
        all_text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return all_text
    text = await loop.run_in_executor(None, extract_text, state.file_path)
    state.jd_text = text
    return state
