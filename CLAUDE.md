# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Set OPENAI_API_KEY and optionally DB_CONNECTION_STRING in .env
```

## Running

**CLI:**
```bash
python run.py "How many students are enrolled per department?"
python run.py "Top 5 professors by course count" --stream
python run.py "List all students" --db "postgresql://user:pass@localhost/mydb" --execute
```

**API server:**
```bash
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Tests

```bash
pytest tests/ -v
pytest tests/ -v -k "TestPromptTemplates"
pytest tests/ -v -k "TestTools"
pytest tests/ -v -k "TestGraphRouting"
pytest tests/ -v -k "TestBenchmark"
```

## Architecture

A five-agent LangGraph pipeline that converts English questions to validated PostgreSQL SELECT statements.

**Pipeline flow:**

```
English Query
  → [Agent 1: Schema Agent]    — introspects DB / parses OpenAPI / uses pre-built schema (cached)
  → [Agent 2: Query Agent]     — extracts semantic structure (intent, filters, joins, aggregations)
  → [Agent 3: SQL Generator]   — generates SELECT from schema + key points
  → [Agent 4: Validator]       — 4-layer check: syntax → schema refs → EXPLAIN → LLM semantic
      ↳ on failure: loops back to Agent 3 with error context (up to MAX_RETRIES)
  → [Finalise Node]            — sets status: success or failed
  → [Agent 5: Executor]        — optional; runs SQL when execute_query=True
```

**Key files:**
- `state/graph_state.py` — `GraphState` TypedDict; all agents read/write from this shared state
- `graph/pipeline_graph.py` — LangGraph `StateGraph` wiring: nodes, conditional edges, retry logic
- `agents/` — One file per agent; each node function takes/returns `GraphState`
- `prompts/templates.py` — All 5 `ChatPromptTemplate` definitions (generator has two: initial + retry)
- `tools/db_tools.py` — LangChain `@tool` functions: schema fetch, syntax/schema validation, EXPLAIN, execute
- `api/main.py` — FastAPI app with `/query`, `/execute`, `/schema`, `/health` endpoints
- `run.py` — Public API (`run_pipeline`, `stream_pipeline`) and CLI entry point

**Schema sources** (configured per request or via env):
- PostgreSQL live introspection (psycopg2)
- OpenAPI 3.x spec (URL, local file, or dict) → mapped to pseudo-SQL types
- Pre-built `SchemaContext` object passed directly

**Validation layers in `agents/validator.py`:**
1. sqlglot syntax parse + write-operation guard (blocks INSERT/UPDATE/DELETE/DROP)
2. sqlglot AST — verify all table/column references exist in schema
3. PostgreSQL `EXPLAIN` dry-run (optional, requires live DB)
4. LLM semantic check — does the SQL answer the original question?

**Retry mechanism:** `graph/pipeline_graph.py:should_retry()` checks `validation_passed` and `retry_count < MAX_RETRIES`. On retry, Agent 3 receives the validator's error message via `SQL_RETRY_PROMPT`.

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | required | |
| `OPENAI_MODEL` | `gpt-4o` | |
| `DB_CONNECTION_STRING` | — | PostgreSQL DSN; optional if using OpenAPI schema |
| `MAX_RETRIES` | `3` | Validator→generator retry attempts |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | Schema introspection cache lifetime |
| `LOG_LEVEL` | `INFO` | |
| `EXECUTOR_MAX_ROWS` | `500` | Row limit for Agent 5 results |

## Sample Database

`college_schema.sql` defines a 10-table PostgreSQL schema (departments, professors, courses, students, enrollments, exams, exam_results, library_books, book_issues, hostels) useful for local testing.
