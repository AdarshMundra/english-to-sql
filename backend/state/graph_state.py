"""
state/graph_state.py  (v3 — execution result fields added)
"""
from __future__ import annotations
from typing import Any, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    row_count: Optional[int] = None


class SchemaContext(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class QueryKeyPoints(BaseModel):
    intent: str = "fetch"
    tables_hint: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    aggregations: list[str] = Field(default_factory=list)
    sort: Optional[str] = None
    limit: Optional[int] = None
    join_hint: list[str] = Field(default_factory=list)
    raw_query: str = ""


class QueryResult(BaseModel):
    """Structured result from Agent 5 — SQL Executor."""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False          # True when result > MAX_ROWS
    execution_time_ms: float = 0.0
    error: Optional[str] = None      # set if execution failed


class GraphState(TypedDict, total=False):
    # ── Inputs ────────────────────────────────────────────────────────────────
    english_query: str
    schema_source: str               # "db" | "openapi_url" | "openapi_file" | "openapi_dict"
    connection_string: str
    openapi_url: str
    openapi_file: str
    openapi_spec: dict[str, Any]
    execute_query: bool              # NEW: whether Agent 5 should run the SQL

    # ── Agent 1 ───────────────────────────────────────────────────────────────
    schema_context: Optional[SchemaContext]

    # ── Agent 2 ───────────────────────────────────────────────────────────────
    query_key_points: Optional[QueryKeyPoints]

    # ── Agent 3 ───────────────────────────────────────────────────────────────
    generated_sql: Optional[str]

    # ── Agent 4 ───────────────────────────────────────────────────────────────
    validation_passed: bool
    validation_error: Optional[str]
    retry_count: int
    max_retries: int

    # ── Agent 5 (new) ─────────────────────────────────────────────────────────
    query_result: Optional[QueryResult]
    execution_error: Optional[str]

    # ── Final ─────────────────────────────────────────────────────────────────
    final_sql: Optional[str]
    status: str
    metadata: dict[str, Any]
