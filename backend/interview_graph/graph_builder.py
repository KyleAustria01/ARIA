"""
graph_builder — Builds the ARIA MVP 2.0 LangGraph interview pipeline.

Two separate graphs are built:

1. setup_graph — Run once by the recruiter after upload:
   analyze_jd → analyze_resume → research → merge_context
   Returns a fully populated InterviewState ready for the interview.

2. interview_graph — Run per-turn during the live interview:
   question → (applicant answers via WebSocket) → evaluate_answer
   → router → [continue: question | finalize: final_evaluation]

The interview_graph uses a conditional edge on router_node:
  is_complete=False → question_node (loop)
  is_complete=True  → final_evaluation_node (end)
"""

import logging

from langgraph.graph import StateGraph, END

from backend.interview_graph.state import InterviewState
from backend.interview_graph.analyze_jd_node import analyze_jd_node
from backend.interview_graph.analyze_resume_node import analyze_resume_node
from backend.interview_graph.research_node import research_node
from backend.interview_graph.merge_context_node import merge_context_node
from backend.interview_graph.question_node import question_node
from backend.interview_graph.evaluate_answer_node import evaluate_answer_node
from backend.interview_graph.router_node import router_node
from backend.interview_graph.final_evaluation_node import final_evaluation_node

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


def _route(state: InterviewState) -> str:
    """Conditional edge function for router_node.

    Args:
        state: Current InterviewState after router_node updates is_complete.

    Returns:
        "finalize" if interview should end, "continue" to loop back.
    """
    return "finalize" if state.is_complete else "continue"


def build_interview_graph() -> StateGraph:
    """Build the per-turn interview graph (question → evaluate → route).

    Flow:
        question → evaluate_answer → router
            ├── continue → question  (loop)
            └── finalize → final_evaluation → END

    This graph is invoked once per applicant answer turn via the WebSocket.

    Returns:
        Compiled LangGraph StateGraph for the live interview phase.
    """
    graph = StateGraph(InterviewState)

    graph.add_node("question", question_node)
    graph.add_node("evaluate_answer", evaluate_answer_node)
    graph.add_node("router", router_node)
    graph.add_node("final_evaluation", final_evaluation_node)

    graph.set_entry_point("question")
    graph.add_edge("question", "evaluate_answer")
    graph.add_edge("evaluate_answer", "router")

    graph.add_conditional_edges(
        "router",
        _route,
        {
            "continue": "question",
            "finalize": "final_evaluation",
        },
    )

    graph.add_edge("final_evaluation", END)

    logger.info("Interview graph compiled")
    return graph.compile()


# Module-level compiled graph instances (imported by websocket handler)
setup_graph = build_setup_graph()
interview_graph = build_interview_graph()

