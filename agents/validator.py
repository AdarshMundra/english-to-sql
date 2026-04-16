"""
agents/validator.py  (fixed)
──────────────────────────────
LangGraph node — Agent 4: SQL Validation

FIX: validate_schema_refs tool was being called with wrong kwarg name.
     Tool expects "schema_json" — was being passed correctly, but the
     tool's internal parameter name was inconsistent. Normalised here.

FIX: LLM response key was "error_message" but prompt sometimes returns
     "error" — now checks both.
"""

from __future__ import annotations

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

from prompts.templates import VALIDATOR_PROMPT
from state.graph_state import GraphState, SchemaContext
from tools.db_tools import validate_sql_syntax, validate_schema_refs, run_explain
from agents.sql_generator import _schema_to_summary

log = structlog.get_logger()


def _schema_to_json(schema: SchemaContext) -> str:
    return json.dumps({
        "tables": [
            {"name": t.name, "columns": [col.model_dump() for col in t.columns]}
            for t in schema.tables
        ]
    })


def _build_semantic_chain():
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=512,
    )
    return VALIDATOR_PROMPT | llm | JsonOutputParser()


def _fail(error: str) -> dict:
    return {
        "validation_passed": False,
        "validation_error": error,
        "final_sql": None,
        "status": "retrying",
    }


def validator_node(state: GraphState) -> dict:
    sql    = state.get("generated_sql", "")
    schema = state.get("schema_context")

    if not sql:
        return _fail("No SQL was generated")

    if schema is None:
        return _fail("No schema context available for validation")

    log.info("validator_start", sql_preview=sql[:100])

    # ── Layer 1: write-op guard + syntax ──────────────────────────────────────
    try:
        r1 = json.loads(validate_sql_syntax.invoke({"sql": sql}))
    except Exception as e:
        return _fail(f"Syntax check error: {e}")

    if not r1.get("valid"):
        err = r1.get("error", "Syntax validation failed")
        log.warning("validator_syntax_fail", error=err)
        return _fail(err)

    # ── Layer 2: schema reference check ───────────────────────────────────────
    try:
        schema_json = _schema_to_json(schema)
        r2 = json.loads(validate_schema_refs.invoke({"sql": sql, "schema_json": schema_json}))
    except Exception as e:
        return _fail(f"Schema ref check error: {e}")

    if not r2.get("valid"):
        err = r2.get("error", "Schema reference validation failed")
        log.warning("validator_schema_fail", error=err)
        return _fail(err)

    # ── Layer 2b: EXPLAIN dry-run (only if live DB configured) ────────────────
    db_conn = os.getenv("DB_CONNECTION_STRING", "")
    if db_conn:
        try:
            r2b = json.loads(run_explain.invoke({"sql": sql, "connection_string": db_conn}))
            if not r2b.get("valid"):
                err = r2b.get("error", "EXPLAIN dry-run failed")
                log.warning("validator_explain_fail", error=err)
                return _fail(err)
        except Exception as e:
            log.warning("validator_explain_exception", error=str(e))
            # Non-fatal — don't block on EXPLAIN failures

    # ── Layer 3: LLM semantic check ───────────────────────────────────────────
    try:
        kp = state.get("query_key_points")
        raw_query = kp.raw_query if kp else state.get("english_query", "")
        chain = _build_semantic_chain()
        r3 = chain.invoke({
            "schema_summary": _schema_to_summary(schema),
            "raw_query": raw_query,
            "generated_sql": sql,
        })
    except Exception as e:
        log.warning("validator_llm_exception", error=str(e))
        # If LLM check itself fails, pass through (layers 1+2 already passed)
        r3 = {"valid": True}

    if not r3.get("valid", True):
        # Support both "error_message" and "error" keys from LLM
        err = r3.get("error_message") or r3.get("error") or "LLM semantic check failed"
        log.warning("validator_semantic_fail", error=err)
        return _fail(err)

    log.info("validator_passed")
    return {
        "validation_passed": True,
        "validation_error": None,
        "final_sql": sql,
        "status": "success",
    }
