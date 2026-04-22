# Backend — Complete Developer Guide

## Folder Structure

```
backend/
├── agents/
│   ├── __init__.py
│   ├── schema_agent.py        # Agent 1 — DB schema understanding
│   ├── query_agent.py         # Agent 2 — English query understanding
│   ├── sql_generator.py       # Agent 3 — SQL generation
│   ├── validator.py           # Agent 4 — 4-layer SQL validation
│   ├── executor_agent.py      # Agent 5 — SQL execution
│   └── schema_sources/
│       ├── __init__.py
│       └── openapi_schema.py  # OpenAPI 3.x spec → SchemaContext converter
├── api/
│   ├── __init__.py
│   └── main.py                # FastAPI application
├── graph/
│   ├── __init__.py
│   └── pipeline_graph.py      # LangGraph StateGraph wiring
├── prompts/
│   ├── __init__.py
│   └── templates.py           # All 5 ChatPromptTemplates
├── state/
│   ├── __init__.py
│   └── graph_state.py         # GraphState TypedDict + Pydantic models
├── tools/
│   ├── __init__.py
│   └── db_tools.py            # LangChain @tool definitions
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py       # Full test suite (unit + integration)
├── college_schema.sql          # 10-table sample database
├── run.py                      # Public API + CLI entry point
├── requirements.txt
├── .env.example
└── BACKEND_DOCS.md
```

---

## state/graph_state.py

The single source of truth for all data flowing through the pipeline. Every agent reads from and writes to `GraphState`.

### Pydantic Models

```python
ColumnInfo      # one column: name, data_type, nullable, is_primary_key, is_foreign_key, references
TableInfo       # one table: name, columns[], row_count
SchemaContext   # tables[], relationships[]
QueryKeyPoints  # intent, tables_hint, filters, aggregations, sort, limit, join_hint, raw_query
QueryResult     # columns, rows, row_count, truncated, execution_time_ms, error
```

### GraphState TypedDict

```python
class GraphState(TypedDict, total=False):
    # Inputs
    english_query: str
    schema_source: str          # "db" | "openapi_url" | "openapi_file" | "openapi_dict"
    connection_string: str
    openapi_url: str
    openapi_file: str
    openapi_spec: dict
    execute_query: bool

    # Agent 1 output
    schema_context: SchemaContext

    # Agent 2 output
    query_key_points: QueryKeyPoints

    # Agent 3 output
    generated_sql: str

    # Agent 4 output
    validation_passed: bool
    validation_error: str
    retry_count: int
    max_retries: int

    # Agent 5 output
    query_result: QueryResult
    execution_error: str

    # Final
    final_sql: str
    status: str          # "running" | "success" | "failed" | "retrying"
    metadata: dict
```

---

## graph/pipeline_graph.py

Wires the five agents into a `StateGraph`. The key function is `should_retry()`:

```python
def should_retry(state: GraphState) -> str:
    if state.get("validation_passed"):
        return "end"            # proceed to finalise
    if retry_count <= max_retries:
        return "sql_generator"  # loop back with error context
    return "end"                # exhausted — mark as failed
```

**Graph edges:**
```
START → schema_agent → query_agent → sql_generator → validator
                                              ↑            │
                                              └────────────┘ (retry)
                                                            │ (pass)
                                                        finalise → executor_agent → END
```

The graph is compiled once and cached in `_compiled_graph` (singleton via `get_graph()`).

---

## agents/schema_agent.py — Agent 1

**Responsibility:** Build a `SchemaContext` from the chosen schema source.

**Short-circuit:** If `schema_context` is already in `GraphState` (pre-built by the API), the node returns `{}` immediately — no DB call, no LLM call.

**Schema source routing:**
| `schema_source` value | What happens |
|---|---|
| `"db"` | psycopg2 → `information_schema` queries → LLM cleans JSON |
| `"openapi_url"` | `urllib.request.urlopen` → `openapi_schema.from_url()` |
| `"openapi_file"` | `Path.read_text()` → `openapi_schema.from_file()` |
| `"openapi_dict"` | `openapi_schema.from_dict()` |

**Caching:** SHA-256 hash of the connection string / URL / file path is the cache key. TTL = `SCHEMA_CACHE_TTL_SECONDS` (default 3600s).

**LLM chain (DB source only):**
```
SCHEMA_AGENT_PROMPT | ChatOpenAI(gpt-4o, max_tokens=4096) | JsonOutputParser
```
Input: raw JSON from `fetch_db_schema` tool.
Output: `{"tables": [...], "relationships": [...]}` → parsed into `SchemaContext`.

---

## agents/query_agent.py — Agent 2

**Responsibility:** Parse English intent into a structured `QueryKeyPoints`.

**Chain:**
```
QUERY_AGENT_PROMPT | ChatOpenAI(gpt-4o, max_tokens=1024) | JsonOutputParser
```

**Output fields:**
- `intent`: `fetch | count | aggregate | rank`
- `tables_hint`: table names the LLM thinks are relevant
- `filters`: plain-English conditions
- `aggregations`: e.g. `["COUNT(*)", "SUM(revenue)"]`
- `sort`: e.g. `"cgpa DESC"`
- `limit`: integer or null
- `join_hint`: natural language join descriptions
- `raw_query`: verbatim original question (always echoed back)

---

## agents/sql_generator.py — Agent 3

**Responsibility:** Generate or fix a PostgreSQL SELECT statement.

**Two prompt paths:**
- **First attempt** (`validation_error` is None): uses `SQL_GENERATOR_PROMPT`
- **Retry** (`validation_error` is set): uses `SQL_RETRY_PROMPT` (includes previous SQL + error)

**Chain:**
```
SQL_GENERATOR_PROMPT / SQL_RETRY_PROMPT | ChatOpenAI(gpt-4o, max_tokens=1024) | StrOutputParser
```

**`_schema_to_summary()`** converts `SchemaContext` into a readable text block:
```
Table: students (~16 rows)
  student_id: integer NOT NULL  [PK]
  department_id: integer  [FK→departments.department_id]
  cgpa: numeric
```

**`_strip_fences()`** strips markdown code fences if the LLM wraps its output in ` ```sql ... ``` `.

On each run:
- Increments `retry_count`
- Clears `validation_error` and `validation_passed` so the validator starts fresh

---

## agents/validator.py — Agent 4

**Responsibility:** Four-layer validation of the generated SQL.

### Layer 1 — Write-op guard + syntax
```python
validate_sql_syntax.invoke({"sql": sql})
```
- Regex rejects INSERT / UPDATE / DELETE / DROP / TRUNCATE / ALTER / CREATE / REPLACE / MERGE
- `sqlglot.parse_one(sql, dialect="postgres")` catches syntax errors
- Returns `{"valid": true}` or `{"valid": false, "error": "..."}`

### Layer 2 — Schema reference check
```python
validate_schema_refs.invoke({"sql": sql, "schema_json": schema_json})
```
- Parses the SQL AST with sqlglot
- Walks all `sqlglot.exp.Table` and `sqlglot.exp.Column` nodes
- Every referenced table and column must exist in `SchemaContext`

### Layer 2b — EXPLAIN dry-run (optional)
```python
run_explain.invoke({"sql": sql, "connection_string": db_conn})
```
- Only runs if `DB_CONNECTION_STRING` is set
- Executes `EXPLAIN <sql>` (no ANALYZE, no data read)
- Catches join type mismatches, wrong column types that passed AST check
- Non-fatal: exceptions here do not block the pipeline

### Layer 3 — LLM semantic check
```python
VALIDATOR_PROMPT | ChatOpenAI(gpt-4o, max_tokens=512) | JsonOutputParser
```
- Asks: "Does this SQL correctly answer the original English question?"
- Returns `{"valid": true}` or `{"valid": false, "error_message": "..."}`
- If the LLM call itself throws, validation passes (layers 1+2 already passed)

**On failure:** returns `_fail(error)` which sets:
```python
{"validation_passed": False, "validation_error": error, "final_sql": None, "status": "retrying"}
```

**On success:**
```python
{"validation_passed": True, "validation_error": None, "final_sql": sql, "status": "success"}
```

---

## agents/executor_agent.py — Agent 5

**Responsibility:** Run the validated SQL and return rows.

**Guards (all must pass to execute):**
1. `execute_query == True` in state
2. A `connection_string` is available (state or `DB_CONNECTION_STRING` env var)
3. `validation_passed == True`
4. `final_sql` or `generated_sql` is not empty

**Uses `execute_sql` tool:**
- Opens a read-only psycopg2 session (`conn.set_session(readonly=True)`)
- `fetchmany(max_rows + 1)` — fetches one extra row to detect truncation
- Serialises results: `Decimal → float`, `datetime → str`, `None → None`
- Returns `QueryResult` Pydantic model

**Row limit:** `EXECUTOR_MAX_ROWS` env var (default 500).

---

## tools/db_tools.py

LangChain `@tool` functions used by agent nodes.

### `fetch_db_schema(connection_string)`
Queries `information_schema.columns`, primary key constraints, foreign key constraints, and `pg_stat_user_tables` for row counts. Returns raw JSON.

### `validate_sql_syntax(sql)`
Write-op regex + sqlglot parse. Returns JSON.

### `validate_schema_refs(sql, schema_json)`
sqlglot AST walk. Returns JSON.

### `run_explain(sql, connection_string)`
`EXPLAIN <sql>` against live DB. Returns JSON.

### `execute_sql(sql, connection_string, max_rows=500)`
Read-only SELECT execution. Returns JSON with columns, rows, row_count, truncated, execution_time_ms, error.

All tools return JSON strings (not dicts) so they can be used both by agent nodes (`json.loads(tool.invoke(...))`) and directly by the LLM via LangChain's tool-calling interface.

**`_sanitize_dsn(dsn)`** — re-encodes special characters in PostgreSQL passwords before passing to psycopg2.

---

## prompts/templates.py

All five `ChatPromptTemplate` definitions. Each has a `SystemMessagePromptTemplate` (persona + rules) and a `HumanMessagePromptTemplate` (dynamic variables).

| Template | Input Variables | Output Format |
|---|---|---|
| `SCHEMA_AGENT_PROMPT` | `raw_schema_json` | JSON `{tables, relationships}` |
| `QUERY_AGENT_PROMPT` | `english_query` | JSON `QueryKeyPoints` |
| `SQL_GENERATOR_PROMPT` | `schema_summary, raw_query, key_points_json` | Raw SQL string |
| `SQL_RETRY_PROMPT` | `schema_summary, raw_query, key_points_json, previous_sql, error_message` | Raw SQL string |
| `VALIDATOR_PROMPT` | `schema_summary, raw_query, generated_sql` | JSON `{valid, error_message}` |

Rules enforced in prompts:
- SELECT only, no write ops
- Only tables/columns from the provided schema
- Explicit JOIN ... ON syntax
- Table aliases on multi-table queries
- `date_trunc()` for PostgreSQL time filters
- JSON output only — no explanation, no markdown

---

## api/main.py — FastAPI Application

### Pydantic Request/Response Models

```python
QueryRequest          # english_query, schema_source, connection_string, openapi_url, max_retries, execute_query
OpenAPIQueryRequest   # english_query, openapi_url, max_retries, execute_query
DirectExecuteRequest  # sql, connection_string, max_rows
SchemaPreviewRequest  # schema_source, connection_string, openapi_url
QueryResponse         # status, sql, attempts, elapsed_s, error, query_result, execution_error
QueryResultOut        # columns, rows, row_count, truncated, execution_time_ms, error
SchemaOut             # table_count, column_count, relationships, tables[]
```

### Endpoints

**`GET /health`**
Returns `{"status": "ok", "version": "3.0.0", "openai_model": "gpt-4o"}`.

**`POST /query`**
Main endpoint. Accepts any schema source. Calls `run_pipeline()`.
- If `schema_source=db`: requires `connection_string` (body or env var)
- If `schema_source=openapi_url`: pre-fetches schema via `from_url()`, passes as `schema_context`

**`POST /query/openapi-url`**
Convenience endpoint: always uses OpenAPI URL schema.

**`POST /query/openapi-file`**
Accepts a multipart file upload. Detects YAML vs JSON from filename.

**`POST /execute`**
Bypasses the pipeline. Calls `execute_sql` tool directly.
Write ops are still blocked by the tool's regex guard.

**`POST /schema/preview`**
Returns a full `SchemaOut` without running a query. Useful for the Schema Browser tab.

### CORS
```python
allow_origins=["*"]  # open for development; restrict in production
```

### Global exception handler
Any unhandled exception → `{"error": "ExceptionClassName", "detail": "message"}` with 500 status.

---

## run.py — Public API & CLI

### `run_pipeline(english_query, ...)`

The main entry point for programmatic use. Builds `GraphState`, calls `get_graph().invoke()`, returns:

```python
{
    "status": "success" | "failed",
    "sql": "<SQL string or None>",
    "attempts": <int>,
    "error": "<validation error or None>",
    "elapsed_s": <float>,
    "query_result": {...}   # only if execute_query=True
}
```

### `stream_pipeline(english_query, ...)`

Uses `graph.stream()` to print node-by-node output to stdout as the pipeline runs. Useful for CLI debugging.

### CLI

```bash
python run.py "query" [--db DSN] [--openapi-url URL] [--openapi-file PATH]
                      [--retries N] [--execute] [--stream]
```

---

## agents/schema_sources/openapi_schema.py

Converts OpenAPI 3.x specs into `SchemaContext` without a database.

**Type mapping:**

| OpenAPI type + format | PostgreSQL type |
|---|---|
| `string` | `varchar` |
| `string / date` | `date` |
| `string / date-time` | `timestamp` |
| `string / uuid` | `uuid` |
| `integer` | `integer` |
| `integer / int64` | `bigint` |
| `number` | `numeric` |
| `boolean` | `boolean` |
| `array` / `object` | `jsonb` |

**$ref detection:** Properties with `$ref` become foreign key columns (`ref_table_id → ref_table.id`).

**Name conversion:** PascalCase / camelCase schema names → snake_case table names.

**Path harvesting:** Inline requestBody and response schemas from `paths` are also extracted if they aren't already in `components/schemas`.

Loaders: `from_dict()`, `from_file()`, `from_url()`, `from_string()`.

---

## tests/test_pipeline.py

Pytest test suite with 7 test classes:

| Class | What it tests |
|---|---|
| `TestPromptTemplates` | Template variables and formatting |
| `TestTools` | `validate_sql_syntax`, `validate_schema_refs` (no LLM, no DB) |
| `TestSQLGeneratorNode` | `_schema_to_summary`, `_strip_fences`, node with mocked LLM |
| `TestValidatorNode` | All 4 validation layers with mocked LLM |
| `TestGraphRouting` | `should_retry()` logic, graph compiles with expected nodes |
| `TestEndToEnd` | Full pipeline with all LLMs mocked |
| `TestBenchmark` | 4 hand-verified SQL queries through programmatic validation layers |
| `TestExecutorAgent` | All guard conditions (no execute flag, no connection, not validated) |
| `TestExecuteSqlTool` | Write-op rejection (no real DB needed) |
| `TestQueryResultModel` | Pydantic model defaults and construction |

Run specific suites:
```bash
pytest tests/ -v -k "TestPromptTemplates"
pytest tests/ -v -k "TestTools"
pytest tests/ -v -k "TestGraphRouting"
pytest tests/ -v -k "TestBenchmark"
```

---

## college_schema.sql — Sample Database

10 tables with realistic data for testing:

| Table | Rows | Key columns |
|---|---|---|
| `departments` | 7 | name, code, building, hod_name |
| `hostels` | 4 | name, type (boys/girls), capacity |
| `professors` | 12 | first_name, last_name, department_id, salary, designation |
| `courses` | 16 | code, name, department_id, professor_id, credits, semester |
| `students` | 16 | roll_number, department_id, hostel_id, cgpa, admission_year |
| `enrollments` | 27 | student_id, course_id, status (active/dropped/completed) |
| `exams` | 12 | course_id, exam_type, exam_date, total_marks |
| `exam_results` | 24 | student_id, exam_id, marks_obtained, grade |
| `library_books` | 10 | title, author, isbn, department_id, total/available copies |
| `book_issues` | 10 | student_id, book_id, issued_on, due_date, fine_amount |

Indexes on all common join/filter columns (`department_id`, `student_id`, `course_id`, etc.).

---

## Dependencies (requirements.txt)

```
langchain>=0.2.0          # LangChain core
langchain-core>=0.2.0
langchain-openai>=0.1.0   # ChatOpenAI
langchain-community>=0.2.0
langgraph>=0.1.0          # StateGraph orchestration
fastapi>=0.111.0          # REST API
uvicorn[standard]>=0.30.0 # ASGI server
python-multipart>=0.0.9   # file uploads
psycopg2-binary>=2.9.9    # PostgreSQL driver
sqlglot>=23.0.0           # SQL parser/AST
python-dotenv>=1.0.0      # .env loading
pydantic>=2.6.0           # data models
structlog>=24.1.0         # structured logging
pyyaml>=6.0.1             # YAML OpenAPI parsing
pytest>=8.0.0             # tests
pytest-asyncio>=0.23.0
httpx>=0.27.0             # async HTTP in tests
```

---

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | required | Must be set before starting |
| `OPENAI_MODEL` | `gpt-4o` | All agents use this model |
| `DB_CONNECTION_STRING` | — | PostgreSQL DSN; optional if using OpenAPI schema |
| `MAX_RETRIES` | `3` | Max validation retries (1–10 via API) |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | Schema cache duration in seconds |
| `LOG_LEVEL` | `INFO` | structlog level |
| `EXECUTOR_MAX_ROWS` | `500` | Hard row cap for Agent 5 |

---

## Data Flow Through the Pipeline

```
english_query: "How many students per department?"

Agent 1 → schema_context: {tables: [departments, students, ...], relationships: [...]}

Agent 2 → query_key_points: {
  intent: "count",
  tables_hint: ["students", "departments"],
  filters: [],
  aggregations: ["COUNT(*)"],
  sort: "count DESC",
  join_hint: ["students joined to departments on department_id"]
}

Agent 3 → generated_sql: """
  SELECT d.name, COUNT(s.student_id) AS student_count
  FROM departments d
  LEFT JOIN students s ON s.department_id = d.department_id
  GROUP BY d.name
  ORDER BY student_count DESC
"""

Agent 4 → validation_passed: true, final_sql: <same as above>

Agent 5 → query_result: {
  columns: ["name", "student_count"],
  rows: [["Computer Science", 7], ["Electronics Engineering", 3], ...],
  row_count: 7,
  execution_time_ms: 4.2
}
```
