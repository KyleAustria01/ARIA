"""
LangGraph builder for ARIA AI Interview System.
Wires all LangGraph nodes into a graph for orchestration.
"""
from langgraph.state import InterviewState
from langgraph.upload_jd_node import upload_jd_node
from langgraph.parse_pdf_node import parse_pdf_node
from langgraph.research_node import research_node
from langgraph.merge_context_node import merge_context_node
from langgraph.intro_node import intro_node
from langgraph.question_node import question_node
from langgraph.evaluate_answer_node import evaluate_answer_node
from langgraph.router_node import router_node
from langgraph.final_evaluation_node import final_evaluation_node
from langgraph.graph import StateGraph


def build_interview_graph() -> StateGraph:
    """
    Build and return the LangGraph interview orchestration graph.
    Returns:
        StateGraph: Configured LangGraph graph.
    """
    graph = StateGraph(InterviewState)
    graph.add_node("upload_jd_node", upload_jd_node)
    graph.add_node("parse_pdf_node", parse_pdf_node)
    graph.add_node("research_node", research_node)
    graph.add_node("merge_context_node", merge_context_node)
    graph.add_node("intro_node", intro_node)
    graph.add_node("question_node", question_node)
    graph.add_node("evaluate_answer_node", evaluate_answer_node)
    graph.add_node("router_node", router_node)
    graph.add_node("final_evaluation_node", final_evaluation_node)
    # Define edges/transitions as needed
    # Example: graph.add_edge("upload_jd_node", "parse_pdf_node")
    return graph
