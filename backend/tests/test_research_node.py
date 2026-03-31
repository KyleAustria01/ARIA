"""
Pytest tests for research_node in ARIA AI Interview System.
"""
import pytest
from backend.langgraph.state import InterviewState
from backend.langgraph.research_node import research_node

@pytest.mark.asyncio
async def test_research_node(monkeypatch):
    class DummyTavilyClient:
        async def search(self, query, max_results):
            return {"results": [{"content": "Relevant research 1"}, {"content": "Relevant research 2"}]}
    # Patch TavilyClient in research_node
    import backend.langgraph.research_node as rn
    monkeypatch.setattr(rn, "TavilyClient", lambda api_key: DummyTavilyClient())
    state = InterviewState(jd_text="Test JD")
    state = await research_node(state)
    assert "Relevant research 1" in state.research
    assert "Relevant research 2" in state.research
