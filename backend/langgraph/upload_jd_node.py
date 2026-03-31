"""
LangGraph node: upload_jd_node for ARIA AI Interview System.
Receives and stores uploaded PDF, returns file path in state.
"""
from typing import Dict
from backend.langgraph.state import InterviewState
import os
import aiofiles

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def upload_jd_node(state: InterviewState, file_bytes: bytes, filename: str) -> InterviewState:
    """
    Receives and stores uploaded PDF, returns updated state with file path.
    Args:
        state (InterviewState): Current LangGraph state.
        file_bytes (bytes): PDF file bytes.
        filename (str): Original filename.
    Returns:
        InterviewState: Updated state with file_path set.
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_bytes)
    state.file_path = file_path
    return state
