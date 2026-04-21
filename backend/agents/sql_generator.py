"""
agents/sql_generator.py  (Phase 4)
────────────────────────────────────
LangGraph node — Agent 3: SQL Generation

Uses SQL_GENERATOR_PROMPT for first attempt.
Uses SQL_RETRY_PROMPT when state contains a previous failed SQL + error.

Chain:  (SQL_GENERATOR_PROMPT | SQL_RETRY_PROMPT) | LLM | StrOutputParser
Returns: {"generated_sql": str}
"""

from __future__ import annotations

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from prompts.templates import SQL_GENERATOR_PROMPT, SQL_RETRY_PROMPT
from state.graph_state import GraphState, SchemaContext

log = structlog.get_logger()


def _schema_to_summary(schema: SchemaContext) -> str:
    """Convert SchemaContext into a readable text block for the prompt."""
    lines = []
    for table in schema.tables:
        count_str = f" (~{table.row_count:,} rows)" if table.row_count else ""
        lines.append(f"Table: {table.name}{count_str}")
        for col in table.columns:
            flags = []
            if col.is_primary_key:
                flags.append("PK")
            if col.is_foreign_key:
                flags.append(f"FK→{col.references}")
            not_null = "" if col.nullable else " NOT NULL"
            flag_str = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(f"  {col.name}: {col.data_type}{not_null}{flag_str}")
        lines.append("")

    if schema.relationships:
        lines.append("Relationships:")
        for r in schema.relationships:
            lines.append(f"  {r}")

    return "\n".join(lines)


def _key_points_to_json(state: GraphState) -> str:
    kp = state["query_key_points"]
    return json.dumps({
        "intent": kp.intent,
        "tables_hint": kp.tables_hint,
        "filters": kp.filters,
        "aggregations": kp.aggregations,
        "sort": kp.sort,
        "limit": kp.limit,
        "join_hint": kp.join_hint,
    }, indent=2)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the LLM wrapped its output."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].strip()
        if text.lower().startswith("sql"):
            text = text[3:].strip()
    return text


def _build_chain(is_retry: bool):
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=1024,
    )
    prompt = SQL_RETRY_PROMPT if is_retry else SQL_GENERATOR_PROMPT
    return prompt | llm | StrOutputParser()


def sql_generator_node(state: GraphState) -> dict:
    """
    LangGraph node for Agent 3.
    Chooses SQL_RETRY_PROMPT automatically if state has a previous error.
    Returns {"generated_sql": str, "retry_count": int}.
    """
    is_retry = bool(state.get("validation_error"))
    retry_count = state.get("retry_count", 0)

    log.info("sql_generator_start", is_retry=is_retry, attempt=retry_count + 1)

    schema_summary = _schema_to_summary(state["schema_context"])
    key_points_json = _key_points_to_json(state)
    raw_query = state["query_key_points"].raw_query

    chain = _build_chain(is_retry)

    if is_retry:
        inputs = {
            "schema_summary": schema_summary,
            "raw_query": raw_query,
            "key_points_json": key_points_json,
            "previous_sql": state.get("generated_sql", ""),
            "error_message": state.get("validation_error", ""),
        }
    else:
        inputs = {
            "schema_summary": schema_summary,
            "raw_query": raw_query,
            "key_points_json": key_points_json,
        }

    sql = _strip_fences(chain.invoke(inputs))

    log.info("sql_generator_complete", sql_preview=sql[:120])
    return {
        "generated_sql": sql,
        "retry_count": retry_count + 1,
        # Clear previous error so validator starts fresh
        "validation_error": None,
        "validation_passed": False,
    }
