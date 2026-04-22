# Text-to-SQL Studio — Project Overview

## What It Is

A full-stack web application that converts plain English questions into validated PostgreSQL SELECT statements using a five-agent AI pipeline. Users type a question like *"How many students are enrolled per department?"* and get back correct, validated SQL — optionally executed against a live database to return real rows.

---

## Tech Stack at a Glance

| Layer | Technology |
|---|---|
| AI Orchestration | LangGraph (StateGraph) |
| LLM | OpenAI gpt-4o |
| SQL Validation | sqlglot (AST parser) |
| Backend API | FastAPI (Python) |
| Database Driver | psycopg2 (PostgreSQL) |
| Frontend | React 18 + Vite |
| Styling | CSS Modules |

---

## High-Level Architecture

```
User (Browser)
    │
    │  HTTP POST /query
    ▼
FastAPI (backend/api/main.py)
    │
    │  calls run_pipeline()
    ▼
LangGraph Pipeline (5 agents)
    │
    ├─ Agent 1: Schema Agent     ← reads DB or OpenAPI spec
    ├─ Agent 2: Query Agent      ← understands English intent
    ├─ Agent 3: SQL Generator    ← writes the SQL
    ├─ Agent 4: Validator        ← 4-layer safety check, retries on failure
    └─ Agent 5: Executor         ← optional: runs SQL, returns rows
    │
    ▼
PostgreSQL Database (Neon.tech in production)
```

---

## The Five Agents

### Agent 1 — Schema Agent
Reads the database structure and builds a `SchemaContext` (list of tables, columns, types, foreign keys). Supports three sources:
- **Live PostgreSQL** — introspects `information_schema`
- **OpenAPI 3.x URL/file** — parses spec and maps types to SQL types
- **Pre-built** — caller passes in an existing `SchemaContext` (skip this agent entirely)

Results are cached for 1 hour (configurable via `SCHEMA_CACHE_TTL_SECONDS`).

### Agent 2 — Query Agent
Uses an LLM to extract the semantic structure from the English question: intent (fetch / count / aggregate / rank), table hints, filter conditions, aggregations, sort order, limit, and join hints. Returns a `QueryKeyPoints` object.

### Agent 3 — SQL Generator
Takes the schema summary and key points, generates a valid PostgreSQL SELECT statement. On a retry (validation failed), it receives the previous failing SQL plus the error message and fixes only what's broken.

### Agent 4 — Validator (4 layers)
1. **Write-op guard** — blocks INSERT, UPDATE, DELETE, DROP, etc.
2. **Syntax check** — sqlglot PostgreSQL parser
3. **Schema ref check** — every table and column in the SQL must exist in the schema
4. **EXPLAIN dry-run** — optional, only if a live DB is configured; catches semantic join errors
5. **LLM semantic check** — does the SQL actually answer the question?

On failure: loops back to Agent 3 with the error. Up to `MAX_RETRIES` (default 3) attempts.

### Agent 5 — Executor
Runs the validated SQL against PostgreSQL in a read-only session. Returns columns, rows, row count, truncation flag, and execution time. Only activates when `execute_query=True` in the request.

---

## Retry Loop

```
SQL Generator → Validator
                    │
          validation_passed? ──YES──→ Finalise → Executor → END
                    │
                   NO
                    │
          retry_count < max_retries? ──YES──→ SQL Generator (with error context)
                    │
                   NO
                    │
                 Finalise (status=failed) → END
```

---

## Schema Sources

| Source | How to use |
|---|---|
| `db` | Pass a PostgreSQL connection string; live schema introspection |
| `openapi_url` | Pass a URL to an OpenAPI 3.x JSON/YAML spec |
| `openapi_file` | Upload a `.json` or `.yaml` spec file via the API |
| Pre-built | Pass a `SchemaContext` object directly (skips Agent 1) |

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | API status + model info |
| POST | `/query` | Full pipeline (any schema source) |
| POST | `/query/openapi-url` | Pipeline via OpenAPI URL |
| POST | `/query/openapi-file` | Pipeline via uploaded spec file |
| POST | `/execute` | Run raw SQL directly (no pipeline) |
| POST | `/schema/preview` | Browse schema without querying |

Swagger UI available at `/docs`.

---

## Project Structure

```
text_to_sql_lg/
├── backend/
│   ├── agents/              # One file per agent (5 agents)
│   │   └── schema_sources/  # OpenAPI parser
│   ├── api/                 # FastAPI app (main.py)
│   ├── graph/               # LangGraph pipeline wiring
│   ├── prompts/             # All ChatPromptTemplates
│   ├── state/               # GraphState TypedDict + Pydantic models
│   ├── tools/               # LangChain @tool functions (DB tools)
│   ├── tests/               # pytest test suite
│   ├── college_schema.sql   # Sample 10-table PostgreSQL schema + data
│   ├── run.py               # Public API + CLI entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root component, tab navigation
│   │   └── components/      # QueryPanel, SchemaViewer, SqlExecutor, etc.
│   ├── package.json
│   └── vite.config.js
└── docs/                    # This documentation folder
```

---

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | required | OpenAI authentication |
| `OPENAI_MODEL` | `gpt-4o` | Model used by all agents |
| `DB_CONNECTION_STRING` | — | PostgreSQL DSN |
| `MAX_RETRIES` | `3` | Validator→generator retry cap |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | Schema cache lifetime |
| `EXECUTOR_MAX_ROWS` | `500` | Row limit for Agent 5 |

---

## Sample Database (college_schema.sql)

10 tables for local testing:

```
departments → professors → courses
           → students   → enrollments → courses
                        → book_issues → library_books
                        → exam_results → exams → courses
           → hostels    ← students
```

---

## Running Locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:3000
```

CLI usage:
```bash
python run.py "How many students per department?"
python run.py "Top 5 professors by course count" --stream
python run.py "List all students" --db "postgresql://..." --execute
```
