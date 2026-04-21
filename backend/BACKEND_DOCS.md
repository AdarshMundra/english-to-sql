# Backend — Complete Documentation

> **Who is this for?**
> Anyone — including people with zero programming background — who wants to understand what this backend does, how it works, and why it is structured the way it is.

---

## Table of Contents

1. [What does this system do?](#1-what-does-this-system-do)
2. [The big picture — how a question becomes SQL](#2-the-big-picture--how-a-question-becomes-sql)
3. [Folder and file map](#3-folder-and-file-map)
4. [The shared "memory" — GraphState](#4-the-shared-memory--graphstate)
5. [Agent 1 — Schema Agent](#5-agent-1--schema-agent)
6. [Agent 2 — Query Agent](#6-agent-2--query-agent)
7. [Agent 3 — SQL Generator](#7-agent-3--sql-generator)
8. [Agent 4 — Validator](#8-agent-4--validator)
9. [Agent 5 — Executor Agent](#9-agent-5--executor-agent)
10. [The Pipeline (how agents connect)](#10-the-pipeline-how-agents-connect)
11. [Prompt Templates — what we tell the AI](#11-prompt-templates--what-we-tell-the-ai)
12. [Database Tools](#12-database-tools)
13. [The API Server](#13-the-api-server)
14. [The CLI (run.py)](#14-the-cli-runpy)
15. [OpenAPI Schema Support](#15-openapi-schema-support)
16. [The Sample Database](#16-the-sample-database)
17. [Tests](#17-tests)
18. [Environment Variables (settings)](#18-environment-variables-settings)
19. [Data flow — a worked example](#19-data-flow--a-worked-example)
20. [Security built into the system](#20-security-built-into-the-system)

---

## 1. What does this system do?

Imagine asking a question in plain English — **"How many students are enrolled in Computer Science?"** — and the system automatically writing the correct database query and optionally running it to return the answer.

That is exactly what this backend does. It converts **plain English questions into valid PostgreSQL SELECT statements** using a team of five AI agents that each handle one specific job.

**Plain English in → SQL query out → (optionally) real data back.**

---

## 2. The big picture — how a question becomes SQL

Think of this as an assembly line in a factory. Each station does one specific job and passes its work to the next.

```
You type:
  "How many students are enrolled per department?"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STATION 1 — Schema Agent                                       │
│  "Let me learn what tables and columns exist in the database"   │
│  Output: a structured map of the database                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STATION 2 — Query Agent                                        │
│  "Let me understand what the person is asking for"              │
│  Output: intent=count, tables=[students, departments],          │
│          aggregation=COUNT(*), join=students→departments        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STATION 3 — SQL Generator                                      │
│  "Let me write the SQL query"                                   │
│  Output: SELECT d.name, COUNT(s.student_id)                     │
│          FROM departments d                                     │
│          JOIN students s ON s.department_id = d.department_id  │
│          GROUP BY d.name                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STATION 4 — Validator                                          │
│  "Let me check this SQL is correct and safe"                    │
│  4 checks: syntax → valid table/column names → database test →  │
│            AI semantic check                                    │
│  If FAIL → sends error back to Station 3 for a retry (max 3×)  │
│  If PASS → move on                                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STATION 5 — Executor Agent (optional)                          │
│  "Let me actually run the SQL against the real database"        │
│  Output: columns, rows, row count, timing                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              Final result returned to you
```

---

## 3. Folder and file map

```
backend/
│
├── run.py                         ← Entry point: CLI tool + run_pipeline() function
│
├── .env                           ← Secret settings (API keys, DB address) — not shared
├── .env.example                   ← Template showing what settings are needed
├── requirements.txt               ← List of all software packages this project needs
├── college_schema.sql             ← A sample college database for testing
│
├── state/
│   └── graph_state.py             ← The shared "memory" — all data agents read/write
│
├── graph/
│   └── pipeline_graph.py          ← The wiring — connects agents in order, handles retries
│
├── agents/
│   ├── schema_agent.py            ← Agent 1: reads/understands the database structure
│   ├── query_agent.py             ← Agent 2: understands the English question
│   ├── sql_generator.py           ← Agent 3: writes the SQL
│   ├── validator.py               ← Agent 4: checks/validates the SQL
│   ├── executor_agent.py          ← Agent 5: runs the SQL against the database
│   └── schema_sources/
│       └── openapi_schema.py      ← Helper: converts API specs into database maps
│
├── prompts/
│   └── templates.py               ← The exact instructions given to the AI for each step
│
├── tools/
│   └── db_tools.py                ← Low-level database operations and SQL checkers
│
├── api/
│   └── main.py                    ← Web server: HTTP endpoints for web/frontend use
│
└── tests/
    └── test_pipeline.py           ← Automated tests that verify everything works
```

---

## 4. The shared "memory" — GraphState

**File:** `state/graph_state.py`

All five agents share a single "clipboard" that holds all information about the current request. This is called **GraphState**. Think of it as a form that gets filled in section by section as work progresses.

### Data models (the building blocks)

Before the main state, there are smaller data models that describe structured information:

#### `ColumnInfo` — describes one column in a database table
```
name          → the column's name          (e.g. "student_id")
data_type     → the type of data it holds  (e.g. "integer", "varchar")
nullable      → can this column be empty?  (true/false)
is_primary_key→ is this the unique ID?     (true/false)
is_foreign_key→ does it point to another table? (true/false)
references    → which table.column it points to (e.g. "departments.department_id")
```

#### `TableInfo` — describes one whole table
```
name      → table name           (e.g. "students")
columns   → list of ColumnInfo   (all columns in this table)
row_count → how many rows exist  (e.g. 500)
```

#### `SchemaContext` — describes the entire database structure
```
tables        → list of TableInfo   (all tables)
relationships → list of plain text  (e.g. "students.department_id → departments.department_id")
```

#### `QueryKeyPoints` — the AI's understanding of what the user asked
```
intent       → what kind of query: "fetch" / "count" / "aggregate" / "rank"
tables_hint  → which tables are probably needed
filters      → conditions in plain English (e.g. "city = Mumbai")
aggregations → maths operations needed (e.g. "COUNT(*)", "SUM(salary)")
sort         → how to order results (e.g. "cgpa DESC")
limit        → max number of rows to return (e.g. 10)
join_hint    → how tables are linked
raw_query    → the original question word-for-word
```

#### `QueryResult` — the results from running the SQL
```
columns          → column names of the results
rows             → the actual data rows
row_count        → how many rows came back
truncated        → was the result cut off because there were too many rows?
execution_time_ms→ how long the query took in milliseconds
error            → any error message if it failed
```

### `GraphState` — the main shared clipboard

This is the complete state passed between all agents:

| Field | Set by | Meaning |
|---|---|---|
| `english_query` | You | The original English question |
| `schema_source` | You | Where to get schema: `"db"`, `"openapi_url"`, `"openapi_file"`, `"openapi_dict"` |
| `connection_string` | You | Database address (like a URL for the database) |
| `openapi_url` | You | URL of an OpenAPI spec if using that instead of a live DB |
| `openapi_file` | You | Path to a local OpenAPI file |
| `execute_query` | You | `true` = run the SQL; `false` = just return the SQL text |
| `schema_context` | Agent 1 | The full structured database map |
| `query_key_points` | Agent 2 | The structured understanding of the question |
| `generated_sql` | Agent 3 | The SQL query that was written |
| `validation_passed` | Agent 4 | Did the SQL pass all checks? |
| `validation_error` | Agent 4 | If it failed, what was wrong? |
| `retry_count` | Agent 3/4 | How many times has Agent 3 retried? |
| `max_retries` | You | Maximum retry attempts (default 3) |
| `query_result` | Agent 5 | The actual data rows returned |
| `execution_error` | Agent 5 | Any error during execution |
| `final_sql` | Agent 4 | The SQL that passed validation |
| `status` | Pipeline | `"running"` / `"success"` / `"failed"` |
| `metadata` | System | Extra info (for future use) |

---

## 5. Agent 1 — Schema Agent

**File:** `agents/schema_agent.py`

### What it does
Learns the structure of the database before any query runs. It finds out what tables exist, what columns are in each table, what data types each column holds, and how tables relate to each other.

### Why it's needed
The SQL generator (Agent 3) cannot write correct SQL without knowing what tables and columns actually exist. The schema agent builds this knowledge.

### Three ways it can get the schema

**Option A — Live PostgreSQL database**
Connects directly to the database and reads its structure by querying PostgreSQL's own internal system tables. Results are cached (saved in memory for up to 1 hour) so it doesn't have to reconnect every single time.

**Option B — OpenAPI URL**
Some systems describe their data structure using an OpenAPI specification (a standard format). The agent can fetch this spec from a web URL and convert it into a database schema format.

**Option C — OpenAPI file or dict**
Same as Option B but the spec is loaded from a local file on disk, or passed directly as a Python dictionary.

### Short-circuit (skip)
If the schema is already provided by the caller (e.g. the API pre-built it), the agent skips its work entirely and just passes through — saving time.

### Caching explained
To avoid re-reading the same database structure over and over, the schema is saved in memory. Each cache entry:
- Is keyed by a fingerprint (hash) of the connection string or URL
- Expires after `SCHEMA_CACHE_TTL_SECONDS` (default: 1 hour)
- Can be force-refreshed by calling `run(force_refresh=True)`

### Chain (how it calls the AI)
For live DB schemas: the raw database metadata (a big JSON blob) is passed to GPT-4o with a structured prompt. The AI parses it into the clean `SchemaContext` format.
```
raw PostgreSQL metadata (JSON) → SCHEMA_AGENT_PROMPT → GPT-4o → JsonOutputParser → SchemaContext
```

---

## 6. Agent 2 — Query Agent

**File:** `agents/query_agent.py`

### What it does
Takes the user's plain English question and extracts its structured meaning. It figures out *what* the user wants, *from which tables*, under *what conditions*.

### Why it's needed
SQL requires very precise logic. Before writing SQL, we need to understand:
- Is the user counting things, fetching rows, or calculating averages?
- Which tables are likely involved?
- Are there any filters (e.g. "only students from Delhi")?
- Should results be sorted or limited?

### Example

Input question: `"Top 5 students by CGPA in Computer Science"`

Output (`QueryKeyPoints`):
```json
{
  "intent": "rank",
  "tables_hint": ["students", "departments"],
  "filters": ["departments.name = Computer Science"],
  "aggregations": [],
  "sort": "cgpa DESC",
  "limit": 5,
  "join_hint": ["students joined to departments on department_id"],
  "raw_query": "Top 5 students by CGPA in Computer Science"
}
```

### Chain
```
english_query → QUERY_AGENT_PROMPT → GPT-4o → JsonOutputParser → QueryKeyPoints
```

---

## 7. Agent 3 — SQL Generator

**File:** `agents/sql_generator.py`

### What it does
Takes the database schema (from Agent 1) and the structured query understanding (from Agent 2) and writes a valid SQL SELECT statement.

### Two modes

**First attempt (normal mode)**
Uses `SQL_GENERATOR_PROMPT`. Given the schema and key points, it writes the SQL from scratch.

**Retry mode**
If Agent 4 (Validator) rejects the SQL, Agent 3 is called again with `SQL_RETRY_PROMPT`. This prompt includes:
- The original question
- The previous failed SQL
- The specific error message from validation

The AI is told to fix *only* the described error rather than rewrite from scratch.

### How it formats the schema for the AI
It converts `SchemaContext` into a human-readable text block:
```
Table: students (~500 rows)
  student_id: integer NOT NULL [PK]
  department_id: integer NOT NULL [FK→departments.department_id]
  first_name: varchar
  cgpa: numeric
  ...
```

### Markdown fence stripping
GPT-4o sometimes wraps its SQL output in markdown code fences like:
```
```sql
SELECT ...
```
```
The `_strip_fences()` function removes these fences so only the raw SQL is kept.

### Output
Returns `{"generated_sql": "SELECT ...", "retry_count": N}` plus resets any previous error state.

---

## 8. Agent 4 — Validator

**File:** `agents/validator.py`

### What it does
Checks whether the generated SQL is correct, safe, and actually answers the user's question. It runs **four independent checks** in order. The SQL must pass all four.

### The four validation layers

#### Layer 1 — Write-operation guard + syntax check
Uses a library called **sqlglot** (a pure-code SQL parser — no database connection needed).

First, it scans the SQL for dangerous words: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `REPLACE`, `MERGE`. If any are found, validation fails immediately with a "Write operation not permitted" error.

Then it parses the SQL to check for syntax errors (missing keywords, mismatched parentheses, etc.).

#### Layer 2 — Schema reference check
Also uses sqlglot to parse the SQL into a tree structure (AST — Abstract Syntax Tree). It walks through every table name and column name mentioned in the SQL and checks that each one actually exists in `SchemaContext`.

If the SQL says `FROM ghost_table` but `ghost_table` doesn't exist in the schema → validation fails.

#### Layer 2b — Live EXPLAIN test (optional)
If a live database connection is available, it runs `EXPLAIN <sql>` against PostgreSQL. This asks PostgreSQL to *plan* the query without *running* it. PostgreSQL will still catch errors like wrong column types, wrong join paths, or ambiguous column names.

This layer is skipped gracefully if no database connection is configured.

#### Layer 3 — LLM semantic check
Sends the SQL, the schema, and the original question to GPT-4o and asks: "Does this SQL actually answer what the user asked?" The AI checks:
- Does the SELECT return the right data?
- Are JOIN conditions correct?
- Are filters and aggregations applied correctly?

If the AI says it's wrong, it provides a specific error message that Agent 3 will use in its retry.

### What happens on failure
```python
_fail("Unknown table: ghost_table")
→ returns {
    "validation_passed": False,
    "validation_error": "Unknown table: ghost_table",
    "final_sql": None,
    "status": "retrying"
  }
```

### What happens on success
```python
→ returns {
    "validation_passed": True,
    "validation_error": None,
    "final_sql": "SELECT ...",
    "status": "success"
  }
```

---

## 9. Agent 5 — Executor Agent

**File:** `agents/executor_agent.py`

### What it does
Runs the validated SQL against a real PostgreSQL database and returns the actual data rows.

### When it runs
Three conditions must ALL be true for it to run:
1. `execute_query` flag is `True` (you have to explicitly ask for execution)
2. A database `connection_string` is available
3. `validation_passed` is `True` (never runs unvalidated SQL)

If any condition fails, the agent quietly skips and returns nothing (or an error message).

### Row limit
It fetches at most `EXECUTOR_MAX_ROWS` rows (default 500, configurable via env var). If the real result has more rows, the `truncated` flag is set to `True` in the response.

### Output format
```json
{
  "columns": ["name", "cgpa"],
  "rows": [["Sneha Patel", 9.1], ["Arjun Sharma", 8.75]],
  "row_count": 2,
  "truncated": false,
  "execution_time_ms": 12.5,
  "error": null
}
```

### Database session safety
When executing, it opens a **read-only database session**. This means even if somehow a write SQL slipped through, the database itself would reject it.

---

## 10. The Pipeline (how agents connect)

**File:** `graph/pipeline_graph.py`

### What is LangGraph?
LangGraph is a library for connecting AI agents in a graph structure. Think of it as flowchart software — you define nodes (agents) and edges (connections between them), and it manages running them in order.

### The pipeline graph

```
START
  │
  ▼
schema_agent ──────────────────────────────────────────────────────────────┐
  │                                                                        │
  ▼                                                                        │
query_agent                                                                │
  │                                                                        │
  ▼                                                                        │
sql_generator ◄──────────────────────────────────────┐                    │
  │                                                   │  retry             │
  ▼                                                   │                    │
validator ──── validation_passed? ──── YES ──► finalise ──► executor ──► END
                      │
                      NO (retries left)
                      │
                      └──────────────────────────────►┘
```

### The retry logic (`should_retry` function)
After the validator runs, the pipeline checks:
- If `validation_passed = True` → go to `finalise`
- If `validation_passed = False` AND `retry_count <= max_retries` → go back to `sql_generator`
- If `validation_passed = False` AND retries exhausted → go to `finalise` (with failed status)

### The `finalise_node`
A tiny intermediate node that sets the final status:
- If validation passed → `status = "success"`
- If validation failed (retries exhausted) → `status = "failed"`, `final_sql = None`

### Compiled graph singleton
The graph is built once and cached (`_compiled_graph`). Every subsequent call reuses the same compiled graph for efficiency.

---

## 11. Prompt Templates — what we tell the AI

**File:** `prompts/templates.py`

Each agent has its own set of instructions given to the AI. These are called **prompt templates**. Each template has two parts:

- **System message** — the agent's persona and rules (never changes)
- **Human message** — the actual data for this specific request (changes every time)

### SCHEMA_AGENT_PROMPT (Agent 1)
**System:** "You are a database schema analyst. Parse raw PostgreSQL metadata and return a clean JSON summary. Skip system tables. RESPOND WITH JSON ONLY."

**Human:** Provides the raw schema JSON extracted from the database.

**Variable:** `{raw_schema_json}`

---

### QUERY_AGENT_PROMPT (Agent 2)
**System:** "You are a natural language query analyser. Extract intent, tables, filters, aggregations, sort, limit, and join hints. Return JSON only."

Defines the four intent types:
- `fetch` — simple row retrieval
- `count` — counting rows ("how many...")
- `aggregate` — SUM/AVG/MAX/MIN
- `rank` — TOP-N with ORDER BY

Includes two worked examples so the AI understands the format.

**Human:** `Analyse this query: "{english_query}"`

**Variable:** `{english_query}`

---

### SQL_GENERATOR_PROMPT (Agent 3 — first attempt)
**System:** Rules for writing SQL:
- SELECT only (never INSERT/UPDATE/DELETE/DROP)
- Use only tables/columns that exist in the schema
- Use explicit `JOIN ... ON` syntax (never implicit comma joins)
- Use table aliases on multi-table queries
- Use `date_trunc()` for time filters
- Return ONLY the raw SQL string

**Human:** Provides schema summary, the original question, and extracted key points.

**Variables:** `{schema_summary}`, `{raw_query}`, `{key_points_json}`

---

### SQL_RETRY_PROMPT (Agent 3 — retry attempt)
**System:** Same rules as above, but specifically in "RETRY MODE". Fix only the specific error described — do not rewrite the whole query.

**Human:** Provides schema, question, key points, the **previous failed SQL**, and the **error message**.

**Variables:** `{schema_summary}`, `{raw_query}`, `{key_points_json}`, `{previous_sql}`, `{error_message}`

---

### VALIDATOR_PROMPT (Agent 4 — LLM semantic check)
**System:** "You are a SQL validator. Check if the SQL correctly answers the question. Check: does it answer what was asked? Are all tables/columns correct? Is JOIN logic right? Are aggregations correct?"

Returns `{"valid": true}` or `{"valid": false, "error_message": "specific description"}`.

**Variables:** `{schema_summary}`, `{raw_query}`, `{generated_sql}`

---

## 12. Database Tools

**File:** `tools/db_tools.py`

These are low-level functions that interact with the database or perform SQL analysis. Each is a LangChain `@tool`, which means they can be called by agents and have automatic input/output handling.

### `fetch_db_schema(connection_string)`
Connects to a PostgreSQL database and reads its structure by querying:
- `information_schema.columns` — all table/column metadata
- `information_schema.table_constraints` + `key_column_usage` — primary and foreign key info
- `pg_stat_user_tables` — approximate row counts

Returns a JSON string with all tables, columns, data types, nullability, PK/FK flags, row counts, and foreign key relationships.

---

### `validate_sql_syntax(sql)`
Pure code check — no database needed.

1. Regex scan for write operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.)
2. sqlglot PostgreSQL dialect parser

Returns `{"valid": true}` or `{"valid": false, "error": "..."}`.

---

### `validate_schema_refs(sql, schema_json)`
Pure code check — no database needed.

Parses the SQL into an AST and extracts every table name and column name mentioned. Then checks each one against the provided schema.

Returns `{"valid": true}` or `{"valid": false, "error": "Unknown table(s): X"}`.

---

### `run_explain(sql, connection_string)`
Runs `EXPLAIN <sql>` against a live PostgreSQL database. PostgreSQL plans but does not execute the query. This catches deeper errors (wrong join types, type mismatches) that the static parser cannot catch.

Returns `{"valid": true}` or `{"valid": false, "error": "..."}`.

---

### `execute_sql(sql, connection_string, max_rows=500)`
Actually runs a validated SQL SELECT against the database.

Safety features:
- Write-operation regex guard (rejects anything that isn't SELECT)
- Opens a **read-only database session** (`readonly=True`)
- Fetches `max_rows + 1` rows to detect if result was truncated
- Converts all values to JSON-safe types (handles `Decimal`, `datetime`, `date`)
- Returns timing information

Returns JSON with `columns`, `rows`, `row_count`, `truncated`, `execution_time_ms`, `error`.

---

## 13. The API Server

**File:** `api/main.py`

The API server exposes the pipeline over HTTP so a web browser, frontend, or other service can use it.

**Run command:** `uvicorn api.main:app --reload --port 8000`
**Interactive docs:** http://localhost:8000/docs (auto-generated by FastAPI)

### Endpoints

#### `GET /health`
Quick check that the server is running.
```json
{"status": "ok", "version": "3.0.0", "openai_model": "gpt-4o"}
```

---

#### `POST /query` — Main endpoint
Runs the full 5-agent pipeline. Accepts a JSON body.

**Request body:**
```json
{
  "english_query": "How many students are enrolled in each department?",
  "schema_source": "db",
  "connection_string": "postgresql://user:pass@localhost/college_db",
  "max_retries": 3,
  "execute_query": false
}
```

**Response:**
```json
{
  "status": "success",
  "sql": "SELECT d.name, COUNT(s.student_id) FROM departments d JOIN students s ...",
  "attempts": 1,
  "elapsed_s": 3.24,
  "error": null,
  "query_result": null
}
```

If `execute_query: true`, the `query_result` field also contains the actual data rows.

**Schema sources:** `"db"`, `"openapi_url"`, `"openapi_file"`

---

#### `POST /query/openapi-url`
Shorter endpoint specifically for OpenAPI URL queries.
```json
{
  "english_query": "List all pets",
  "openapi_url": "https://petstore3.swagger.io/api/v3/openapi.json"
}
```

---

#### `POST /query/openapi-file`
Accepts an uploaded `.json` or `.yaml` OpenAPI spec file plus the query as query parameters. Uses multipart form upload.

---

#### `POST /execute`
Run a raw SQL SELECT directly — **no pipeline, no generation, no validation**. You provide the SQL yourself.

```json
{
  "sql": "SELECT name, cgpa FROM students WHERE cgpa > 8.5",
  "connection_string": "postgresql://...",
  "max_rows": 500
}
```

Useful for testing or when you already have the SQL and just need to run it.

---

#### `POST /schema/preview`
Preview the parsed schema without running a query. Useful to verify that the schema is being read correctly before submitting questions.

Returns a full list of tables, columns, row counts, and relationships.

---

### CORS (Cross-Origin Resource Sharing)
The server allows requests from any domain (`allow_origins=["*"]`). This means the frontend running at `localhost:5173` can freely call the API at `localhost:8000`.

### Error handling
A global exception handler catches any unhandled error and returns:
```json
{"error": "ExceptionType", "detail": "specific error message"}
```

---

## 14. The CLI (run.py)

**File:** `run.py`

Provides two ways to use the pipeline:

### `run_pipeline()` — programmatic function
```python
from run import run_pipeline

result = run_pipeline(
    english_query="How many students are enrolled per department?",
    connection_string="postgresql://user:pass@localhost/college_db",
    execute_query=True,
)
print(result["sql"])
print(result["query_result"])
```

### `stream_pipeline()` — live output version
Prints each agent's work as it completes. Shows SQL preview, validation result, and row count in real time.

### Command-line interface
```bash
# Basic usage
python run.py "How many students are enrolled per department?"

# With a specific database
python run.py "Top 5 professors by salary" --db "postgresql://user:pass@localhost/college_db"

# Also run the SQL and show results
python run.py "List all students" --execute

# Stream output step by step
python run.py "Top 5 professors" --stream

# Use an OpenAPI spec instead of a database
python run.py "List all pets" --openapi-url "https://..."
```

### What `run_pipeline` returns
```python
{
    "status": "success",           # or "failed"
    "sql": "SELECT ...",           # the generated SQL
    "attempts": 1,                 # how many SQL generation attempts
    "error": None,                 # validation error if failed
    "elapsed_s": 3.24,             # total time in seconds
    "query_result": {              # only if execute_query=True
        "columns": [...],
        "rows": [...],
        "row_count": 10,
        "truncated": False,
        "execution_time_ms": 12.5
    }
}
```

---

## 15. OpenAPI Schema Support

**File:** `agents/schema_sources/openapi_schema.py`

### What is OpenAPI?
OpenAPI (formerly Swagger) is a standard way to describe a REST API. It lists all the data models (objects) an API works with. This project can use those model definitions as a substitute for a real database schema.

### How it works
The converter maps OpenAPI data types to SQL types:

| OpenAPI type | SQL type |
|---|---|
| `string` (no format) | `varchar` |
| `string` + `date` | `date` |
| `string` + `date-time` | `timestamp` |
| `string` + `uuid` | `uuid` |
| `integer` | `integer` |
| `integer` + `int64` | `bigint` |
| `number` | `numeric` |
| `boolean` | `boolean` |
| `array` | `jsonb` |
| `object` | `jsonb` |

### Naming convention
OpenAPI uses PascalCase names (e.g. `OrderItem`). The converter changes them to snake_case (e.g. `order_item`) to match PostgreSQL conventions.

### Reference handling (`$ref`)
When an OpenAPI property references another schema (e.g. `Order` has a `customer` property that `$ref`s `Customer`), the converter:
1. Creates a foreign key column `customer_id`
2. Adds a relationship entry: `order.customer_id → customer.id`

### Loading options
- `from_file("openapi.yaml")` — from a local YAML or JSON file
- `from_url("https://...")` — fetches from a URL
- `from_dict({...})` — from a Python dictionary
- `from_string("...", fmt="yaml")` — from a raw string

---

## 16. The Sample Database

**File:** `college_schema.sql`

A complete PostgreSQL database for a college, used for local testing.

### Tables (10 total)

| Table | Purpose | Key columns |
|---|---|---|
| `departments` | Academic departments | department_id, name, code, hod_name |
| `professors` | Faculty members | professor_id, first_name, department_id, salary, designation |
| `courses` | Subjects taught | course_id, code, name, department_id, professor_id, semester, credits |
| `students` | Enrolled students | student_id, roll_number, first_name, department_id, cgpa, admission_year |
| `enrollments` | Which student is in which course | student_id, course_id, status |
| `exams` | Exam schedule | exam_id, course_id, exam_type, exam_date, total_marks |
| `exam_results` | Student exam scores | student_id, exam_id, marks_obtained, grade |
| `library_books` | Books in the library | book_id, title, author, available_copies |
| `book_issues` | Who borrowed which book | student_id, book_id, issued_on, due_date, returned_on, fine_amount |
| `hostels` | Student residences | hostel_id, name, type (boys/girls), capacity |

### Departments included
- Computer Science (CS)
- Electronics Engineering (EC)
- Mechanical Engineering (ME)
- Civil Engineering (CE)
- Mathematics (MATH)
- Physics (PHY)
- MBA

### Sample questions you can ask
- "How many students are enrolled per department?"
- "Top 5 professors by salary"
- "Which students have a CGPA above 8.5?"
- "How many books are available in the library?"
- "List all students who have overdue books"
- "Which course has the most enrollments?"

### How to load it
```bash
psql -U postgres -d college_db -f college_schema.sql
```

---

## 17. Tests

**File:** `tests/test_pipeline.py`

### How to run
```bash
cd backend
pytest tests/ -v                                    # run all tests
pytest tests/ -v -k "TestPromptTemplates"           # only prompt tests
pytest tests/ -v -k "TestTools"                     # only tool tests
pytest tests/ -v -k "TestGraphRouting"              # only routing tests
pytest tests/ -v -k "TestBenchmark"                 # only benchmark tests
```

### Test classes and what they verify

#### `TestPromptTemplates`
Checks that each prompt template:
- Contains all required variables (e.g. `{english_query}`, `{schema_summary}`)
- Formats correctly into messages without errors
- Produces the expected number of messages (system + human)

#### `TestTools`
Checks the database tools work correctly:
- Valid SELECT passes syntax validation
- INSERT / DROP / DELETE are rejected
- Broken SQL is caught as a syntax error
- Known table/column names pass schema reference check
- Unknown table names are correctly flagged

#### `TestSQLGeneratorNode`
- Schema summary includes all expected table names and FK markers
- Markdown fences are stripped correctly from AI output
- The node returns a `generated_sql` field and increments `retry_count`
- Retry mode increments the counter correctly

#### `TestValidatorNode`
- A valid SELECT passes through
- DELETE is rejected
- SQL referencing a non-existent table is rejected
- LLM semantic failure causes the validation to fail

#### `TestGraphRouting`
- When validation fails and retries are available → returns `"sql_generator"`
- When validation passes → returns `"end"`
- When retries are exhausted → returns `"end"`
- The compiled graph contains all expected nodes

#### `TestEndToEnd`
Full pipeline tests with mocked AI (no real OpenAI calls):
- A valid query completes with `status = "success"`
- A query that always references a ghost table eventually fails with `status = "failed"`

#### `TestBenchmark`
Four hand-verified SQL queries are run through the programmatic validation layers (syntax + schema refs) to confirm they pass. This acts as a regression guard — if code changes break these, the test fails.

#### `TestExecutorAgent`
- Agent skips when `execute_query = False`
- Agent skips when validation has not passed
- Agent skips when no connection string is available
- Agent skips when there is no SQL to run

#### `TestExecuteSqlTool`
- `INSERT` is rejected even without a DB connection
- `DELETE` is rejected even without a DB connection

#### `TestQueryResultModel`
- Default `QueryResult` has correct empty values
- A populated `QueryResult` stores values correctly

---

## 18. Environment Variables (settings)

**File:** `.env` (copy from `.env.example`)

| Variable | Default | Required? | Explanation |
|---|---|---|---|
| `OPENAI_API_KEY` | — | **Yes** | Your OpenAI API key to use GPT-4o |
| `OPENAI_MODEL` | `gpt-4o` | No | Which OpenAI model to use |
| `DB_CONNECTION_STRING` | — | No (but needed for DB queries) | PostgreSQL connection string, e.g. `postgresql://user:pass@localhost:5432/dbname` |
| `MAX_RETRIES` | `3` | No | How many times to retry SQL generation if validation fails |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | No | How long (seconds) to cache database schema (1 hour default) |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `EXECUTOR_MAX_ROWS` | `500` | No | Maximum number of rows Agent 5 will return |

### Example `.env` file
```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx
OPENAI_MODEL=gpt-4o
DB_CONNECTION_STRING=postgresql://postgres:password@localhost:5432/college_db
MAX_RETRIES=3
SCHEMA_CACHE_TTL_SECONDS=3600
LOG_LEVEL=INFO
EXECUTOR_MAX_ROWS=500
```

---

## 19. Data flow — a worked example

**Question:** `"Top 3 students by CGPA in Computer Science"`

### Step 1 — You send the request
Via CLI:
```bash
python run.py "Top 3 students by CGPA in Computer Science" --execute
```
Or via API:
```json
POST /query
{
  "english_query": "Top 3 students by CGPA in Computer Science",
  "schema_source": "db",
  "connection_string": "postgresql://...",
  "execute_query": true
}
```

### Step 2 — run_pipeline sets up the initial state
```python
GraphState = {
  "english_query": "Top 3 students by CGPA in Computer Science",
  "schema_source": "db",
  "execute_query": True,
  "retry_count": 0,
  "max_retries": 3,
  "status": "running",
  ...all other fields empty/None...
}
```

### Step 3 — Agent 1 (Schema Agent) runs
Connects to the PostgreSQL database, reads all table/column metadata.
Calls GPT-4o to structure it.

State after Agent 1:
```python
{
  "schema_context": SchemaContext(
    tables=[
      TableInfo(name="students", columns=[...cgpa, department_id...]),
      TableInfo(name="departments", columns=[...department_id, name...]),
      ...8 more tables...
    ],
    relationships=["students.department_id → departments.department_id", ...]
  )
}
```

### Step 4 — Agent 2 (Query Agent) runs
Sends `"Top 3 students by CGPA in Computer Science"` to GPT-4o.

State after Agent 2:
```python
{
  "query_key_points": QueryKeyPoints(
    intent="rank",
    tables_hint=["students", "departments"],
    filters=["departments.name = Computer Science"],
    aggregations=[],
    sort="cgpa DESC",
    limit=3,
    join_hint=["students joined to departments on department_id"],
    raw_query="Top 3 students by CGPA in Computer Science"
  )
}
```

### Step 5 — Agent 3 (SQL Generator) runs
Sends schema summary + key points to GPT-4o.

State after Agent 3:
```python
{
  "generated_sql": """
    SELECT s.first_name, s.last_name, s.cgpa
    FROM students s
    JOIN departments d ON s.department_id = d.department_id
    WHERE d.name = 'Computer Science'
    ORDER BY s.cgpa DESC
    LIMIT 3
  """,
  "retry_count": 1
}
```

### Step 6 — Agent 4 (Validator) runs

**Layer 1:** No INSERT/UPDATE/DELETE/DROP found. sqlglot parses it without errors. ✓

**Layer 2:** AST check — `students` exists ✓, `departments` exists ✓, `first_name` exists ✓, `last_name` exists ✓, `cgpa` exists ✓, `department_id` exists ✓, `name` exists ✓. All references valid. ✓

**Layer 2b:** `EXPLAIN SELECT ...` runs on the live database. No errors. ✓

**Layer 3:** GPT-4o checks — "Does this SQL return the top 3 CS students by CGPA? Yes." → `{"valid": true}` ✓

State after Agent 4:
```python
{
  "validation_passed": True,
  "final_sql": "SELECT s.first_name, ...",
  "status": "success"
}
```

### Step 7 — finalise_node runs
Sets `status = "success"`. (Already set by validator, but this confirms it.)

### Step 8 — Agent 5 (Executor Agent) runs
`execute_query = True`, validation passed, connection available → runs the SQL.

State after Agent 5:
```python
{
  "query_result": QueryResult(
    columns=["first_name", "last_name", "cgpa"],
    rows=[
      ["Sneha", "Patel", 9.10],
      ["Arjun", "Sharma", 8.75],
      ["Ananya", "Gupta", 8.50]
    ],
    row_count=3,
    truncated=False,
    execution_time_ms=8.3,
    error=None
  )
}
```

### Step 9 — Final result returned
```json
{
  "status": "success",
  "sql": "SELECT s.first_name, s.last_name, s.cgpa FROM students s JOIN departments d ON s.department_id = d.department_id WHERE d.name = 'Computer Science' ORDER BY s.cgpa DESC LIMIT 3",
  "attempts": 1,
  "elapsed_s": 4.12,
  "query_result": {
    "columns": ["first_name", "last_name", "cgpa"],
    "rows": [["Sneha", "Patel", 9.1], ["Arjun", "Sharma", 8.75], ["Ananya", "Gupta", 8.5]],
    "row_count": 3,
    "truncated": false,
    "execution_time_ms": 8.3
  }
}
```

---

## 20. Security built into the system

The system has multiple overlapping safety mechanisms to prevent any harmful SQL from being executed.

### Defense layer 1 — Write-operation regex guard (Agent 4, Layer 1)
A regular expression scans for `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `REPLACE`, `MERGE`. Any match immediately fails validation.

### Defense layer 2 — SQL parser guard (Agent 4, Layer 1)
sqlglot parses the SQL. If it can't be parsed as valid SQL, it fails.

### Defense layer 3 — Schema reference guard (Agent 4, Layer 2)
The SQL must only reference tables and columns that actually exist in the known schema. Any hallucinated or injected table name fails here.

### Defense layer 4 — AI semantic guard (Agent 4, Layer 3)
A second AI call independently verifies the SQL makes sense for the question asked.

### Defense layer 5 — Read-only database session (Agent 5)
When executing, the database connection is opened in `readonly=True` mode. Even if a write SQL somehow passed all previous checks, the database itself would reject it at the connection level.

### Defense layer 6 — Execute opt-in
Execution against the database only happens when `execute_query = True` is explicitly set. By default, the pipeline returns only the SQL text with no database execution.

### Defense layer 7 — Row limit
Results are capped at `EXECUTOR_MAX_ROWS` (default 500) to prevent accidentally fetching millions of rows.
