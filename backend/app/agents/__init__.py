"""LLM agents built on agno.

Each module exposes one typed async function. Agents only talk to the model;
they never touch the database - persistence lives in `app/workflows` and
`app/services`. Every agent raises `AgentUnavailable` on failure so the caller
can degrade to a documented fallback instead of blocking the workflow.
"""

from app.agents.llm import AgentUnavailable, llm_available

__all__ = ["AgentUnavailable", "llm_available"]