"""
Pytest tests for parse_pdf_node in ARIA AI Interview System.
"""
import pytest
import os
from backend.langgraph.state import InterviewState
from backend.langgraph.parse_pdf_node import parse_pdf_node

@pytest.mark.asyncio
async def test_parse_pdf_node(tmp_path):
    # Create a dummy PDF file
    import fitz
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello, ARIA!")
    doc.save(str(pdf_path))
    doc.close()

    state = InterviewState(file_path=str(pdf_path))
    state = await parse_pdf_node(state)
    assert "Hello, ARIA!" in state.jd_text
