"""
run.py  (v3 — execute_query support)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import structlog
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from graph.pipeline_graph import get_graph
from state.graph_state import GraphState, SchemaContext

log = structlog.get_logger()


def run_pipeline(
    english_query: str,
    connection_string: str | None = None,
    schema_context: SchemaContext | None = None,
    openapi_url: str | None = None,
    openapi_file: str | None = None,
    max_retries: int | None = None,
    execute_query: bool = False,
) -> dict[str, Any]:
    """
    Run the full text-to-SQL LangGraph pipeline.

    Args:
        english_query:     Natural language question.
        connection_string: PostgreSQL DSN. Falls back to DB_CONNECTION_STRING env var.
        schema_context:    Pre-built SchemaContext — skips Agent 1.
        openapi_url:       OpenAPI spec URL — Agent 1 parses it.
        openapi_file:      Local OpenAPI file path.
        max_retries:       Validation retry cap (default 3).
        execute_query:     If True, Agent 5 runs the validated SQL and returns results.

    Returns dict with keys:
        status, sql, attempts, error, elapsed_s,
        + query_result (dict) when execute_query=True
    """
    start = time.perf_counter()

    if schema_context is not None:
        schema_source = "prebuilt"
    elif openapi_url:
        schema_source = "openapi_url"
    elif openapi_file:
        schema_source = "openapi_file"
    else:
        schema_source = "db"

    initial_state: GraphState = {
        "english_query":    english_query,
        "schema_source":    schema_source,
        "connection_string": connection_string or os.getenv("DB_CONNECTION_STRING", ""),
        "openapi_url":      openapi_url or "",
        "openapi_file":     openapi_file or "",
        "execute_query":    execute_query,
        "max_retries":      max_retries if max_retries is not None else int(os.getenv("MAX_RETRIES", "3")),
        "retry_count":      0,
        "validation_passed": False,
        "validation_error": None,
        "generated_sql":    None,
        "final_sql":        None,
        "query_result":     None,
        "execution_error":  None,
        "status":           "running",
        "metadata":         {},
    }

    if schema_context is not None:
        initial_state["schema_context"] = schema_context

    log.info("pipeline_start", query=english_query[:120], schema_source=schema_source, execute=execute_query)

    graph = get_graph()
    final_state: GraphState = graph.invoke(initial_state)

    elapsed = round(time.perf_counter() - start, 3)
    log.info("pipeline_complete",
             status=final_state.get("status"),
             attempts=final_state.get("retry_count"),
             elapsed_s=elapsed)

    result: dict[str, Any] = {
        "status":    final_state.get("status", "failed"),
        "sql":       final_state.get("final_sql"),
        "attempts":  final_state.get("retry_count", 0),
        "error":     final_state.get("validation_error"),
        "elapsed_s": elapsed,
    }

    # Include execution result when agent 5 ran
    qr = final_state.get("query_result")
    if qr is not None:
        result["query_result"] = qr.model_dump() if hasattr(qr, "model_dump") else qr

    exec_err = final_state.get("execution_error")
    if exec_err:
        result["execution_error"] = exec_err

    return result


def stream_pipeline(
    english_query: str,
    connection_string: str | None = None,
    openapi_url: str | None = None,
    max_retries: int | None = None,
    execute_query: bool = False,
) -> None:
    schema_source = "openapi_url" if openapi_url else "db"
    initial_state: GraphState = {
        "english_query":    english_query,
        "schema_source":    schema_source,
        "connection_string": connection_string or os.getenv("DB_CONNECTION_STRING", ""),
        "openapi_url":      openapi_url or "",
        "openapi_file":     "",
        "execute_query":    execute_query,
        "max_retries":      max_retries if max_retries is not None else int(os.getenv("MAX_RETRIES", "3")),
        "retry_count":      0,
        "validation_passed": False,
        "validation_error": None,
        "generated_sql":    None,
        "final_sql":        None,
        "query_result":     None,
        "execution_error":  None,
        "status":           "running",
        "metadata":         {},
    }

    graph = get_graph()
    print(f'\n Running: "{english_query}"\n')
    for event in graph.stream(initial_state):
        for node_name, node_output in event.items():
            print(f"  [{node_name}]")
            if node_name == "sql_generator" and node_output.get("generated_sql"):
                print(f"    SQL: {node_output['generated_sql'][:100]}")
            if node_name == "validator":
                passed = node_output.get("validation_passed", False)
                err    = node_output.get("validation_error")
                print(f"    Validation: {'PASSED' if passed else f'FAILED — {err}'}")
            if node_name == "executor_agent" and node_output.get("query_result"):
                qr = node_output["query_result"]
                rc = qr.row_count if hasattr(qr, "row_count") else qr.get("row_count", 0)
                print(f"    Rows returned: {rc}")
    print("\n  Done.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Text-to-SQL pipeline CLI")
    parser.add_argument("query",            help="English question")
    parser.add_argument("--db",             help="PostgreSQL DSN")
    parser.add_argument("--openapi-url",    help="OpenAPI spec URL")
    parser.add_argument("--openapi-file",   help="Local OpenAPI spec file path")
    parser.add_argument("--retries",        type=int, default=None)
    parser.add_argument("--execute",        action="store_true", help="Run the SQL and return results")
    parser.add_argument("--stream",         action="store_true")
    args = parser.parse_args()

    if args.stream:
        stream_pipeline(
            english_query=args.query,
            connection_string=args.db,
            openapi_url=args.openapi_url,
            max_retries=args.retries,
            execute_query=args.execute,
        )
    else:
        result = run_pipeline(
            english_query=args.query,
            connection_string=args.db,
            openapi_url=args.openapi_url,
            openapi_file=args.openapi_file,
            max_retries=args.retries,
            execute_query=args.execute,
        )
        print(json.dumps(result, indent=2))
