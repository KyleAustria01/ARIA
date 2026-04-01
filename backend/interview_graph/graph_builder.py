"""
graph_builder — Builds the ARIA MVP 2.0 LangGraph setup pipeline.

The setup_graph is run once by the recruiter after upload:
  analyze_jd → analyze_resume → research → merge_context
  Returns a fully populated InterviewState ready for the interview.

The live interview is driven by the WebSocket handler which calls
individual nodes (question, evaluate_answer, router, final_evaluation)
directly per turn, providing maximum flexibility for conversational flow.
"""

import logging

from langgraph.graph import StateGraph, END

from backend.interview_graph.state import InterviewState
from backend.interview_graph.analyze_jd_node import analyze_jd_node
from backend.interview_graph.analyze_resume_node import analyze_resume_node
from backend.interview_graph.research_node import research_node
from backend.interview_graph.merge_context_node import merge_context_node

logger = logging.getLogger(__name__)


def build_setup_graph() -> StateGraph:
    """Build the recruiter setup graph (JD + Resume analysis + research).

    Flow:
        analyze_jd → analyze_resume → research → merge_context → END

    This graph runs once when the recruiter uploads files and clicks
    "Generate Interview Link". The resulting state is saved to Redis.

    Returns:
        Compiled LangGraph StateGraph for the setup phase.
    """
    graph = StateGraph(InterviewState)

    graph.add_node("analyze_jd", analyze_jd_node)
    graph.add_node("analyze_resume", analyze_resume_node)
    graph.add_node("research", research_node)
    graph.add_node("merge_context", merge_context_node)

    graph.set_entry_point("analyze_jd")
    graph.add_edge("analyze_jd", "analyze_resume")
    graph.add_edge("analyze_resume", "research")
    graph.add_edge("research", "merge_context")
    graph.add_edge("merge_context", END)

    logger.info("Setup graph compiled")
    return graph.compile()


# Module-level compiled graph instance (imported by recruiter API)
setup_graph = build_setup_graph()

