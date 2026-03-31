"""
research_node — LangGraph node for Tavily web research.

Uses the job title and required skills extracted from the JD to search
for role benchmarks, industry standards, and common interview questions.
Populates state.research_context with the aggregated results.
Pure function: takes state, returns updated state dict.
"""

import logging

from backend.config import settings
from backend.interview_graph.state import InterviewState

logger = logging.getLogger(__name__)


async def research_node(state: InterviewState) -> dict:
    """Search the web for interview context relevant to the job role.

    Builds Tavily queries from the parsed job title and required skills,
    runs up to 4 searches, and concatenates the results into a single
    research context string stored in state.research_context.

    If Tavily API key is not configured or all searches fail, returns
    an empty research_context so the interview can still proceed.

    Args:
        state: Current InterviewState. Uses job_title, required_skills,
               and experience_required for query building.

    Returns:
        Dict with key 'research_context' containing aggregated web results.
    """
    if not settings.tavily_api_key:
        logger.warning("research_node: TAVILY_API_KEY not set — skipping research")
        return {"research_context": ""}

    from tavily import TavilyClient  # deferred import — optional dependency

    job_title = state.job_title or "Software Developer"
    skills_preview = ", ".join(state.required_skills[:5]) if state.required_skills else ""
    experience = state.experience_required or ""

    queries = [
        f"{job_title} interview questions {experience}".strip(),
        f"{job_title} required skills and competencies",
        f"common {job_title} technical interview questions",
    ]
    if skills_preview:
        queries.append(f"{skills_preview} interview assessment questions")

    client = TavilyClient(api_key=settings.tavily_api_key)
    chunks: list[str] = []

    for query in queries:
        try:
            results = client.search(query=query, max_results=3)
            for r in results.get("results", []):
                content = r.get("content", "").strip()
                if content:
                    chunks.append(content)
            logger.debug("Tavily query OK: %s (%d results)", query, len(results.get("results", [])))
        except Exception as e:
            logger.warning("Tavily query failed for '%s': %s", query, e)
            continue

    research_context = "\n\n".join(chunks)
    logger.info(
        "research_node complete — %d chunks, %d chars",
        len(chunks),
        len(research_context),
    )
    return {"research_context": research_context}

