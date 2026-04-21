"""
graph/pipeline_graph.py  (v3 — Agent 5 added)
──────────────────────────────────────────────
Full pipeline flow:

  START
    → schema_agent   (Agent 1 — schema, short-circuits if pre-built)
    → query_agent    (Agent 2 — English → key points)
    → sql_generator  (Agent 3 — key points + schema → SQL)
    → validator      (Agent 4 — syntax + schema refs + LLM semantic)
         ├─ FAIL + retries left → sql_generator  (retry loop)
         └─ PASS / exhausted  → finalise
                                  → executor_agent  (Agent 5 — run SQL if requested)
                                  → END
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.graph import StateGraph, START, END

from state.graph_state import GraphState
from agents.schema_agent    import schema_agent_node
from agents.query_agent     import query_agent_node
from agents.sql_generator   import sql_generator_node
from agents.validator       import validator_node
from agents.executor_agent  import executor_agent_node


def should_retry(state: GraphState) -> str:
    if state.get("validation_passed"):
        return "end"
    max_retries = state.get("max_retries", int(os.getenv("MAX_RETRIES", "3")))
    retry_count = state.get("retry_count", 0)
    if retry_count <= max_retries:
        return "sql_generator"
    return "end"


def finalise_node(state: GraphState) -> dict:
    """Set final status after validation loop ends."""
    if state.get("validation_passed"):
        return {"status": "success"}
    return {"status": "failed", "final_sql": None}


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("schema_agent",    schema_agent_node)
    graph.add_node("query_agent",     query_agent_node)
    graph.add_node("sql_generator",   sql_generator_node)
    graph.add_node("validator",       validator_node)
    graph.add_node("finalise",        finalise_node)
    graph.add_node("executor_agent",  executor_agent_node)   # Agent 5

    # Main sequential flow
    graph.add_edge(START,            "schema_agent")
    graph.add_edge("schema_agent",   "query_agent")
    graph.add_edge("query_agent",    "sql_generator")
    graph.add_edge("sql_generator",  "validator")

    # Retry or finalise
    graph.add_conditional_edges(
        "validator",
        should_retry,
        {
            "sql_generator": "sql_generator",
            "end":           "finalise",
        },
    )

    # finalise → executor → END
    graph.add_edge("finalise",       "executor_agent")
    graph.add_edge("executor_agent", END)

    return graph.compile()


_compiled_graph = None

def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
