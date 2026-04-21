"""
agents/schema_agent.py  (fixed)
────────────────────────────────
LangGraph node — Agent 1: DB Schema Understanding

FIX: Added short-circuit when schema_context already exists in state
     (schema_source = "prebuilt"). This lets the API pre-build the schema
     from OpenAPI and inject it, skipping the DB call entirely.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

from prompts.templates import SCHEMA_AGENT_PROMPT
from state.graph_state import GraphState, SchemaContext, TableInfo, ColumnInfo
from tools.db_tools import fetch_db_schema
from agents.schema_sources.openapi_schema import (
    from_url, from_file, from_dict as openapi_from_dict
)

log = structlog.get_logger()

_schema_cache: dict[str, tuple[SchemaContext, float]] = {}
_TTL = int(os.getenv("SCHEMA_CACHE_TTL_SECONDS", "3600"))


def _cache_key(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:16]


def _get_cached(key: str) -> SchemaContext | None:
    entry = _schema_cache.get(key)
    if not entry:
        return None
    schema, ts = entry
    if time.time() - ts > _TTL:
        del _schema_cache[key]
        return None
    return schema


def _set_cached(key: str, schema: SchemaContext) -> None:
    _schema_cache[key] = (schema, time.time())


def _build_chain():
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        max_tokens=4096,
    )
    return SCHEMA_AGENT_PROMPT | llm | JsonOutputParser()


def _parse_llm_schema(structured: dict) -> SchemaContext:
    tables = [
        TableInfo(
            name=t["name"],
            row_count=t.get("row_count"),
            columns=[ColumnInfo(**col) for col in t.get("columns", [])],
        )
        for t in structured.get("tables", [])
    ]
    return SchemaContext(tables=tables, relationships=structured.get("relationships", []))


def _from_db(conn: str) -> SchemaContext:
    key = _cache_key(conn)
    cached = _get_cached(key)
    if cached:
        log.info("schema_cache_hit", source="db")
        return cached
    raw: str = fetch_db_schema.invoke({"connection_string": conn})
    chain = _build_chain()
    structured = chain.invoke({"raw_schema_json": raw})
    schema = _parse_llm_schema(structured)
    _set_cached(key, schema)
    return schema


def _from_openapi_url(url: str) -> SchemaContext:
    key = _cache_key(url)
    cached = _get_cached(key)
    if cached:
        return cached
    schema = from_url(url)
    _set_cached(key, schema)
    return schema


def _from_openapi_file(path: str) -> SchemaContext:
    key = _cache_key(path)
    cached = _get_cached(key)
    if cached:
        return cached
    schema = from_file(path)
    _set_cached(key, schema)
    return schema


def schema_agent_node(state: GraphState) -> dict:
    """
    LangGraph node for Agent 1.

    Short-circuits immediately if schema_context is already in state
    (e.g. pre-built by the API from an OpenAPI spec).
    """
    # ── Short-circuit: schema already provided ────────────────────────────────
    if state.get("schema_context") is not None:
        log.info("schema_agent_skip", reason="schema_context already in state")
        return {}   # nothing to update

    source = state.get("schema_source", "db")
    log.info("schema_agent_start", source=source)

    if source == "db":
        conn = state.get("connection_string") or os.getenv("DB_CONNECTION_STRING", "")
        if not conn:
            raise ValueError(
                "connection_string is required when schema_source='db'. "
                "Set DB_CONNECTION_STRING in .env or pass it explicitly."
            )
        schema = _from_db(conn)

    elif source == "openapi_url":
        url = state.get("openapi_url", "")
        if not url:
            raise ValueError("openapi_url is required when schema_source='openapi_url'")
        schema = _from_openapi_url(url)

    elif source == "openapi_file":
        path = state.get("openapi_file", "")
        if not path:
            raise ValueError("openapi_file is required when schema_source='openapi_file'")
        schema = _from_openapi_file(path)

    elif source == "openapi_dict":
        spec = state.get("openapi_spec", {})
        if not spec:
            raise ValueError("openapi_spec is required when schema_source='openapi_dict'")
        schema = openapi_from_dict(spec)

    else:
        raise ValueError(f"Unknown schema_source: '{source}'")

    log.info("schema_agent_complete", source=source, table_count=len(schema.tables))
    return {"schema_context": schema}


def run(
    connection_string: str | None = None,
    openapi_url: str | None = None,
    openapi_file: str | None = None,
    openapi_spec: dict | None = None,
    force_refresh: bool = False,
) -> SchemaContext:
    """Standalone helper — call Agent 1 without running the full pipeline."""
    if force_refresh:
        _schema_cache.clear()
    if openapi_url:
        return _from_openapi_url(openapi_url)
    if openapi_file:
        return _from_openapi_file(openapi_file)
    if openapi_spec:
        return openapi_from_dict(openapi_spec)
    conn = connection_string or os.getenv("DB_CONNECTION_STRING", "")
    if conn:
        return _from_db(conn)
    raise ValueError("Provide one of: connection_string, openapi_url, openapi_file, openapi_spec")


def get_cache_info() -> dict:
    """Return metadata about the currently cached schema (if any)."""
    now = time.time()
    valid = [(k, v) for k, v in _schema_cache.items() if now - v[1] <= _TTL]
    if not valid:
        return {"loaded": False, "table_count": 0, "column_count": 0, "loaded_at": None, "ttl_remaining_s": 0}
    _, (schema, ts) = max(valid, key=lambda x: x[1][1])
    return {
        "loaded": True,
        "table_count": len(schema.tables),
        "column_count": sum(len(t.columns) for t in schema.tables),
        "loaded_at": ts,
        "ttl_remaining_s": int(_TTL - (now - ts)),
    }


def clear_cache() -> None:
    """Force-clear the schema cache (used by force_refresh and tests)."""
    _schema_cache.clear()
