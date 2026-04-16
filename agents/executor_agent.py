"""
agents/executor_agent.py
─────────────────────────
LangGraph node — Agent 5: SQL Executor

Runs the validated SQL against the live PostgreSQL database and stores
the result as a QueryResult in GraphState.

Only runs when:
  1. state["validation_passed"] is True
  2. state["execute_query"] is True
  3. state["connection_string"] is set (or DB_CONNECTION_STRING env var)

If execute_query is False (default), the node is a no-op — the pipeline
behaves exactly as before and just returns the SQL.

MAX_ROWS is configurable via the EXECUTOR_MAX_ROWS env var (default 500).
"""

from __future__ import annotations

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog

from state.graph_state import GraphState, QueryResult
from tools.db_tools import execute_sql

log = structlog.get_logger()

MAX_ROWS = int(os.getenv("EXECUTOR_MAX_ROWS", "500"))


def executor_agent_node(state: GraphState) -> dict:
    """
    LangGraph node for Agent 5.

    Skips silently if:
      - execute_query flag is False / not set
      - no connection_string available
      - validation did not pass (safety guard)

    Returns: {"query_result": QueryResult, "execution_error": str|None}
    """
    # ── Guard: only execute if explicitly requested ────────────────────────────
    if not state.get("execute_query", False):
        log.info("executor_skip", reason="execute_query=False")
        return {}

    # ── Guard: must have a live DB connection ─────────────────────────────────
    conn = state.get("connection_string") or os.getenv("DB_CONNECTION_STRING", "")
    if not conn:
        log.warning("executor_skip", reason="no connection_string")
        return {
            "execution_error": "No database connection available. Set connection_string or DB_CONNECTION_STRING.",
            "query_result": QueryResult(error="No database connection available."),
        }

    # ── Guard: only run validated SQL ─────────────────────────────────────────
    if not state.get("validation_passed", False):
        log.warning("executor_skip", reason="validation_passed=False")
        return {
            "execution_error": "SQL did not pass validation — execution skipped.",
            "query_result": QueryResult(error="Validation failed — execution skipped."),
        }

    sql = state.get("final_sql") or state.get("generated_sql", "")
    if not sql:
        return {
            "execution_error": "No SQL to execute.",
            "query_result": QueryResult(error="No SQL to execute."),
        }

    log.info("executor_start", sql_preview=sql[:100], max_rows=MAX_ROWS)

    # ── Execute via the LangChain tool ────────────────────────────────────────
    raw = execute_sql.invoke({
        "sql": sql,
        "connection_string": conn,
        "max_rows": MAX_ROWS,
    })
    result_dict = json.loads(raw)

    query_result = QueryResult(
        columns=result_dict.get("columns", []),
        rows=result_dict.get("rows", []),
        row_count=result_dict.get("row_count", 0),
        truncated=result_dict.get("truncated", False),
        execution_time_ms=result_dict.get("execution_time_ms", 0.0),
        error=result_dict.get("error"),
    )

    if query_result.error:
        log.error("executor_failed", error=query_result.error)
        return {
            "execution_error": query_result.error,
            "query_result": query_result,
        }

    log.info(
        "executor_complete",
        row_count=query_result.row_count,
        truncated=query_result.truncated,
        elapsed_ms=query_result.execution_time_ms,
    )
    return {
        "query_result": query_result,
        "execution_error": None,
    }
