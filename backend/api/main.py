"""
api/main.py  (v3 — Agent 5 / SQL executor added)
──────────────────────────────────────────────────
FastAPI application exposing the text-to-SQL pipeline.

New in v3:
  - execute_query flag on all /query endpoints
  - QueryResult included in response when execute_query=True
  - POST /execute — run SQL directly against the DB (no pipeline)

Run:
  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import json
import os
import sys
from enum import Enum
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from run import run_pipeline
from agents.schema_agent import run as get_schema, get_cache_info
from agents.schema_sources.openapi_schema import from_string as openapi_from_string

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Text-to-SQL API",
    description="""
Convert natural language questions into validated PostgreSQL SELECT statements
using a five-agent LangGraph pipeline powered by OpenAI gpt-4o.

## Agents
| # | Name | Role |
|---|------|------|
| 1 | Schema agent | Reads DB or OpenAPI spec to build schema context |
| 2 | Query agent | Extracts intent, filters, joins from English |
| 3 | SQL generator | Generates a SELECT statement |
| 4 | Validator | Checks syntax, schema refs, LLM semantic — retries on failure |
| 5 | Executor | Runs the validated SQL and returns rows (opt-in) |

## Schema sources
- **db** — live PostgreSQL database
- **openapi_url** — public OpenAPI 3.x spec URL
- **openapi_file** — uploaded `.json` / `.yaml` spec file
""",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


# ── Models ────────────────────────────────────────────────────────────────────

class SchemaSourceEnum(str, Enum):
    db          = "db"
    openapi_url = "openapi_url"
    openapi_file= "openapi_file"


class QueryResultOut(BaseModel):
    columns:          list[str]
    rows:             list[list[Any]]
    row_count:        int
    truncated:        bool
    execution_time_ms: float
    error:            Optional[str] = None


class QueryResponse(BaseModel):
    status:          str
    sql:             Optional[str]   = None
    attempts:        int
    elapsed_s:       float
    error:           Optional[str]   = None
    query_result:    Optional[QueryResultOut] = None   # populated when execute_query=True
    execution_error: Optional[str]   = None


class QueryRequest(BaseModel):
    english_query: str = Field(
        ...,
        examples=["How many students are enrolled in each department?"],
    )
    schema_source: SchemaSourceEnum = Field(SchemaSourceEnum.db)
    connection_string: Optional[str] = Field(
        None,
        examples=["postgresql://postgres:secret@localhost:5432/college_db"],
    )
    openapi_url: Optional[str] = Field(
        None,
        examples=["https://petstore3.swagger.io/api/v3/openapi.json"],
    )
    max_retries:   int  = Field(3, ge=1, le=10)
    execute_query: bool = Field(
        False,
        description="Set to true to execute the generated SQL and return rows",
    )


class OpenAPIQueryRequest(BaseModel):
    english_query: str  = Field(..., examples=["List all students with CGPA above 8"])
    openapi_url:   str  = Field(..., examples=["https://petstore3.swagger.io/api/v3/openapi.json"])
    max_retries:   int  = Field(3, ge=1, le=10)
    execute_query: bool = Field(False)


class DirectExecuteRequest(BaseModel):
    """Execute a raw SQL statement directly (no pipeline)."""
    sql: str = Field(
        ...,
        description="SQL SELECT statement to execute",
        examples=["SELECT name, cgpa FROM students WHERE cgpa > 8.5 ORDER BY cgpa DESC LIMIT 10"],
    )
    connection_string: Optional[str] = Field(
        None,
        examples=["postgresql://postgres:secret@localhost:5432/college_db"],
    )
    max_rows: int = Field(500, ge=1, le=5000)


class SchemaPreviewRequest(BaseModel):
    schema_source:     SchemaSourceEnum = SchemaSourceEnum.db
    connection_string: Optional[str]    = None
    openapi_url:       Optional[str]    = None


class ColumnOut(BaseModel):
    name:          str
    data_type:     str
    nullable:      bool
    is_primary_key:bool
    is_foreign_key:bool
    references:    Optional[str] = None


class TableOut(BaseModel):
    name:      str
    row_count: Optional[int] = None
    columns:   list[ColumnOut]


class SchemaOut(BaseModel):
    table_count:   int
    column_count:  int
    relationships: list[str]
    tables:        list[TableOut]


class SchemaLoadResponse(BaseModel):
    loaded:        bool
    table_count:   int
    column_count:  int
    loaded_at:     float
    ttl_remaining_s: int
    message:       str


class SchemaStatusResponse(BaseModel):
    loaded:        bool
    table_count:   int
    column_count:  int
    loaded_at:     Optional[float] = None
    ttl_remaining_s: int


class HealthResponse(BaseModel):
    status:      str
    version:     str
    openai_model:str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_query_response(result: dict) -> QueryResponse:
    qr_raw = result.get("query_result")
    qr_out = QueryResultOut(**qr_raw) if isinstance(qr_raw, dict) else None
    return QueryResponse(
        status=result["status"],
        sql=result.get("sql"),
        attempts=result["attempts"],
        elapsed_s=result["elapsed_s"],
        error=result.get("error"),
        query_result=qr_out,
        execution_error=result.get("execution_error"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    return HealthResponse(
        status="ok",
        version="3.0.0",
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    )


@app.post(
    "/query",
    response_model=QueryResponse,
    tags=["pipeline"],
    summary="Run text-to-SQL pipeline (any schema source)",
)
def run_query(body: QueryRequest):
    try:
        kwargs: dict[str, Any] = {
            "english_query": body.english_query,
            "max_retries":   body.max_retries,
            "execute_query": body.execute_query,
        }

        if body.schema_source == SchemaSourceEnum.db:
            conn = body.connection_string or os.getenv("DB_CONNECTION_STRING", "")
            if not conn:
                raise HTTPException(
                    status_code=422,
                    detail="connection_string required when schema_source='db'. "
                           "Pass it in the body or set DB_CONNECTION_STRING in .env",
                )
            kwargs["connection_string"] = conn

        elif body.schema_source == SchemaSourceEnum.openapi_url:
            if not body.openapi_url:
                raise HTTPException(status_code=422, detail="openapi_url required")
            try:
                from agents.schema_sources.openapi_schema import from_url
                kwargs["schema_context"] = from_url(body.openapi_url)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to parse OpenAPI spec: {exc}")

        result = run_pipeline(**kwargs)
        return _build_query_response(result)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/query/openapi-url",
    response_model=QueryResponse,
    tags=["pipeline"],
    summary="Text-to-SQL using an OpenAPI spec URL",
)
def run_query_openapi_url(body: OpenAPIQueryRequest):
    try:
        from agents.schema_sources.openapi_schema import from_url
        schema = from_url(body.openapi_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse OpenAPI spec: {exc}")
    try:
        result = run_pipeline(
            english_query=body.english_query,
            schema_context=schema,
            max_retries=body.max_retries,
            execute_query=body.execute_query,
        )
        return _build_query_response(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/query/openapi-file",
    response_model=QueryResponse,
    tags=["pipeline"],
    summary="Text-to-SQL using an uploaded OpenAPI spec file",
)
async def run_query_openapi_file(
    english_query: str      = Query(...),
    max_retries:   int      = Query(3, ge=1, le=10),
    execute_query: bool     = Query(False, description="Execute the SQL and return rows"),
    spec_file: UploadFile   = File(...),
):
    content = await spec_file.read()
    fmt = "yaml" if spec_file.filename and spec_file.filename.endswith((".yaml",".yml")) else "json"
    try:
        schema = openapi_from_string(content.decode("utf-8"), fmt=fmt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded spec: {exc}")
    try:
        result = run_pipeline(
            english_query=english_query,
            schema_context=schema,
            max_retries=max_retries,
            execute_query=execute_query,
        )
        return _build_query_response(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/execute",
    response_model=QueryResultOut,
    tags=["executor"],
    summary="Execute a SQL statement directly (no pipeline)",
    description=(
        "Run a raw SQL SELECT statement against the database. "
        "No generation or validation pipeline is involved. "
        "Only SELECT is permitted — write operations are blocked."
    ),
)
def execute_direct(body: DirectExecuteRequest):
    from tools.db_tools import execute_sql
    conn = body.connection_string or os.getenv("DB_CONNECTION_STRING", "")
    if not conn:
        raise HTTPException(
            status_code=422,
            detail="connection_string required. Pass it in the body or set DB_CONNECTION_STRING in .env",
        )
    try:
        raw    = execute_sql.invoke({"sql": body.sql, "connection_string": conn, "max_rows": body.max_rows})
        result = json.loads(raw)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return QueryResultOut(**result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post(
    "/schema/preview",
    response_model=SchemaOut,
    tags=["schema"],
    summary="Preview schema without running a query",
)
def preview_schema(body: SchemaPreviewRequest):
    try:
        if body.schema_source == SchemaSourceEnum.db:
            conn = body.connection_string or os.getenv("DB_CONNECTION_STRING", "")
            if not conn:
                raise HTTPException(status_code=422, detail="connection_string required")
            schema = get_schema(connection_string=conn)
        elif body.schema_source == SchemaSourceEnum.openapi_url:
            if not body.openapi_url:
                raise HTTPException(status_code=422, detail="openapi_url required")
            schema = get_schema(openapi_url=body.openapi_url)
        else:
            raise HTTPException(status_code=422, detail="schema_source must be 'db' or 'openapi_url'")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SchemaOut(
        table_count=len(schema.tables),
        column_count=sum(len(t.columns) for t in schema.tables),
        relationships=schema.relationships,
        tables=[
            TableOut(
                name=t.name,
                row_count=t.row_count,
                columns=[ColumnOut(**c.model_dump()) for c in t.columns],
            )
            for t in schema.tables
        ],
    )


@app.post(
    "/schema/load",
    response_model=SchemaLoadResponse,
    tags=["schema"],
    summary="Pre-load schema into server-side cache",
    description=(
        "Runs Agent 1 (Schema Agent) immediately and stores the result in the "
        "in-process cache. All subsequent `/query` calls will skip Agent 1 and "
        "use the cached schema, significantly reducing response time. "
        "Cache expires after `SCHEMA_CACHE_TTL_SECONDS` (default 1 hour)."
    ),
)
def load_schema(body: SchemaPreviewRequest):
    try:
        if body.schema_source == SchemaSourceEnum.db:
            conn = body.connection_string or os.getenv("DB_CONNECTION_STRING", "")
            if not conn:
                raise HTTPException(status_code=422, detail="connection_string required")
            schema = get_schema(connection_string=conn)
        elif body.schema_source == SchemaSourceEnum.openapi_url:
            if not body.openapi_url:
                raise HTTPException(status_code=422, detail="openapi_url required")
            schema = get_schema(openapi_url=body.openapi_url)
        else:
            raise HTTPException(status_code=422, detail="schema_source must be 'db' or 'openapi_url'")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    info = get_cache_info()
    tc = len(schema.tables)
    cc = sum(len(t.columns) for t in schema.tables)
    return SchemaLoadResponse(
        loaded=True,
        table_count=tc,
        column_count=cc,
        loaded_at=info.get("loaded_at", 0.0),
        ttl_remaining_s=info.get("ttl_remaining_s", 0),
        message=f"Schema cached: {tc} tables, {cc} columns",
    )


@app.get(
    "/schema/status",
    response_model=SchemaStatusResponse,
    tags=["schema"],
    summary="Check whether schema is currently cached",
    description=(
        "Returns whether Agent 1's output is present in the in-process cache. "
        "When `loaded=true`, `/query` calls will skip Agent 1 entirely."
    ),
)
def schema_status():
    info = get_cache_info()
    return SchemaStatusResponse(
        loaded=info["loaded"],
        table_count=info.get("table_count", 0),
        column_count=info.get("column_count", 0),
        loaded_at=info.get("loaded_at"),
        ttl_remaining_s=info.get("ttl_remaining_s", 0),
    )
