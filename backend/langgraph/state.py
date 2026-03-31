"""
LangGraph state schema for ARIA AI Interview System.
Defines the typed state shared between nodes.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class InterviewState(BaseModel):
    """
    Typed state for LangGraph interview flow.
    """
    file_path: Optional[str] = None
    jd_text: Optional[str] = None
    research: Optional[str] = None
    context: Optional[str] = None
    applicant_name: Optional[str] = None
    role: Optional[str] = None
    questions: List[str] = []
    answers: List[str] = []
    scores: List[Dict[str, Any]] = []
    verdict: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = []
