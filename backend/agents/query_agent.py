"""
agents/query_agent.py  (Phase 3)
─────────────────────────────────
LangGraph node — Agent 2: English Query Understanding

Chain:  QUERY_AGENT_PROMPT | LLM | JsonOutputParser
Returns partial GraphState update: {"query_key_points": QueryKeyPoints}
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

from prompts.templates import QUERY_AGENT_PROMPT
from state.graph_state import GraphState, QueryKeyPoints

log = structlog.get_logger()


def _build_chain():
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=1024,
    )
    return QUERY_AGENT_PROMPT | llm | JsonOutputParser()


def query_agent_node(state: GraphState) -> dict:
    """
    LangGraph node for Agent 2.
    Reads state["english_query"], returns {"query_key_points": QueryKeyPoints}.
    """
    query = state["english_query"]
    log.info("query_agent_start", query=query[:120])

    chain = _build_chain()
    result: dict = chain.invoke({"english_query": query})

    # Ensure raw_query is always populated
    result.setdefault("raw_query", query)

    key_points = QueryKeyPoints(**result)
    log.info("query_agent_complete", intent=key_points.intent, tables=key_points.tables_hint)

    return {"query_key_points": key_points}
