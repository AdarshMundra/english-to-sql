# Multi-Agent Text-to-SQL — LangChain + LangGraph

Converts English questions into valid PostgreSQL SELECT statements using a five-agent LangGraph pipeline with LangChain prompt templates. Includes a React/Vite frontend for interactive querying.

---

## Project Structure

```
text_to_sql_lg/
│
├── backend/                        # Python API + LangGraph pipeline
│   ├── agents/
│   │   ├── schema_agent.py         # Agent 1 — schema introspection + cache
│   │   ├── query_agent.py          # Agent 2 — query understanding
│   │   ├── sql_generator.py        # Agent 3 — SQL generation (+ retry)
│   │   ├── validator.py            # Agent 4 — 4-layer validation
│   │   ├── executor_agent.py       # Agent 5 — optional SQL execution
│   │   └── schema_sources/
│   │       └── openapi_schema.py   # OpenAPI → SchemaContext parser
│   │
│   ├── api/
│   │   └── main.py                 # FastAPI app (endpoints: /query, /execute, /schema, /health)
│   │
│   ├── graph/
│   │   └── pipeline_graph.py       # StateGraph builder + conditional retry edge
│   │
│   ├── prompts/
│   │   └── templates.py            # All 5 ChatPromptTemplate definitions
│   │
│   ├── state/
│   │   └── graph_state.py          # TypedDict GraphState + Pydantic sub-models
│   │
│   ├── tools/
│   │   └── db_tools.py             # @tool: fetch_db_schema, validate_sql_syntax,
│   │                               #        validate_schema_refs, run_explain, execute_sql
│   │
│   ├── tests/
│   │   └── test_pipeline.py        # Unit + integration + benchmark tests
│   │
│   ├── run.py                      # Public API (run_pipeline, stream_pipeline) + CLI
│   ├── college_schema.sql          # Sample 10-table PostgreSQL schema for local testing
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                        # Local secrets (git-ignored)
│
└── frontend/                       # React + Vite UI
    ├── src/
    │   ├── App.jsx
    │   ├── main.jsx
    │   ├── index.css
    │   └── components/
    │       ├── QueryPanel.jsx       # Natural language input + submit
    │       ├── ResultsTable.jsx     # Query results table
    │       ├── SchemaViewer.jsx     # Database schema browser
    │       ├── SettingsPanel.jsx    # Connection string + settings
    │       ├── SqlBlock.jsx         # Syntax-highlighted SQL display
    │       ├── SqlExecutor.jsx      # Direct SQL execution
    │       └── StatusBar.jsx        # Pipeline status indicator
    ├── dist/                        # Production build output
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Architecture

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

---

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Set OPENAI_API_KEY and optionally DB_CONNECTION_STRING in .env
```

### Run the API server

```bash
cd backend
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Run the CLI

```bash
cd backend
python run.py "How many students are enrolled per department?"
python run.py "Top 5 professors by course count" --stream
python run.py "List all students" --db "postgresql://user:pass@localhost/mydb" --execute
```

### Run as a library

```python
import sys
sys.path.insert(0, "backend")
from run import run_pipeline

result = run_pipeline("How many orders were placed by customers in Mumbai last month?")
print(result)
# {
#   "status": "success",
#   "sql": "SELECT COUNT(*) FROM orders o JOIN ...",
#   "attempts": 1,
#   "error": null,
#   "elapsed_s": 4.2
# }
```

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev      # development server (default: http://localhost:5173)
npm run build    # production build → frontend/dist/
```

The frontend proxies `/query`, `/execute`, `/schema`, and `/health` to the backend at `http://localhost:8000`.

---

## Tests

```bash
cd backend
pytest tests/ -v
pytest tests/ -v -k "TestPromptTemplates"
pytest tests/ -v -k "TestTools"
pytest tests/ -v -k "TestGraphRouting"
pytest tests/ -v -k "TestBenchmark"
```

---

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

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health + model info |
| `POST` | `/query` | Run pipeline (DB or OpenAPI schema source) |
| `POST` | `/query/openapi-url` | Run pipeline using an OpenAPI spec URL |
| `POST` | `/query/openapi-file` | Run pipeline with an uploaded OpenAPI file |
| `POST` | `/execute` | Execute raw SQL directly (no pipeline) |
| `POST` | `/schema/preview` | Preview schema without running a query |

---

## Validation Layers (Agent 4)

| Layer | Method | Catches |
|---|---|---|
| 1 | `validate_sql_syntax` (sqlglot) | Syntax errors, write operations |
| 2 | `validate_schema_refs` (sqlglot AST) | Unknown tables/columns |
| 3 | `run_explain` (psycopg2 EXPLAIN) | Planner-level errors (optional, needs live DB) |
| 4 | `VALIDATOR_PROMPT` + LLM | Semantic correctness vs. the original question |

---

## LangChain Prompt Templates

| Template | File | Used by |
|---|---|---|
| `SCHEMA_AGENT_PROMPT` | prompts/templates.py | Agent 1 — structures raw DB metadata |
| `QUERY_AGENT_PROMPT` | prompts/templates.py | Agent 2 — extracts semantic key points |
| `SQL_GENERATOR_PROMPT` | prompts/templates.py | Agent 3 — first attempt |
| `SQL_RETRY_PROMPT` | prompts/templates.py | Agent 3 — retry with error context |
| `VALIDATOR_PROMPT` | prompts/templates.py | Agent 4 — LLM semantic check |

---

## Sample Database

`backend/college_schema.sql` defines a 10-table PostgreSQL schema:
`departments`, `professors`, `courses`, `students`, `enrollments`, `exams`, `exam_results`, `library_books`, `book_issues`, `hostels`

Useful for local testing.
