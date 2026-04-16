# Multi-Agent Text-to-SQL — LangChain + LangGraph

Converts English questions into valid PostgreSQL SELECT statements
using a four-agent LangGraph pipeline with LangChain prompt templates.

---

## Architecture

```
              START
                │
     ┌──────────┴──────────┐
     ▼                     ▼
schema_agent          query_agent       ← parallel (LangGraph fan-out)
(Agent 1)             (Agent 2)
     └──────────┬──────────┘
                ▼
         sql_generator                  ← Agent 3
         (first attempt)
                │
                ▼
           validator                    ← Agent 4
                │
      ┌─────────┴─────────┐
  passed                failed
      │                   │ (retries left)
      ▼                   ▼
    END           sql_generator         ← Agent 3 (retry with error context)
                  (SQL_RETRY_PROMPT)
```

---

## Project structure

```
text_to_sql_lg/
│
├── prompts/
│   └── templates.py          # All ChatPromptTemplate definitions (5 templates)
│
├── state/
│   └── graph_state.py        # TypedDict GraphState + Pydantic sub-models
│
├── tools/
│   └── db_tools.py           # @tool: fetch_db_schema, validate_sql_syntax,
│                             #        validate_schema_refs, run_explain
│
├── agents/
│   ├── schema_agent.py       # Node: Agent 1 — schema introspection + cache
│   ├── query_agent.py        # Node: Agent 2 — query understanding
│   ├── sql_generator.py      # Node: Agent 3 — SQL generation (+ retry)
│   └── validator.py          # Node: Agent 4 — 3-layer validation
│
├── graph/
│   └── pipeline_graph.py     # StateGraph builder + conditional retry edge
│
├── tests/
│   └── test_pipeline.py      # Unit + integration + benchmark tests
│
├── run.py                    # Public API (run_pipeline) + CLI
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY and DB_CONNECTION_STRING
```

---

## Usage

### As a library

```python
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

### CLI — single query

```bash
python run.py "Top 10 customers by revenue"
```

### CLI — stream node-by-node output

```bash
python run.py "How many out-of-stock products?" --stream
```

### CLI — custom DB and retry count

```bash
python run.py "Average order value per city" \
  --db "postgresql://user:pass@localhost/mydb" \
  --retries 5
```

---

## Running tests

```bash
# All tests
pytest tests/ -v

# Just prompt template tests
pytest tests/ -v -k "TestPromptTemplates"

# Just tool tests
pytest tests/ -v -k "TestTools"

# Graph routing logic
pytest tests/ -v -k "TestGraphRouting"

# Benchmark (known-good SQL pairs)
pytest tests/ -v -k "TestBenchmark"
```

---

## LangChain prompt templates

| Template | File | Used by |
|---|---|---|
| `SCHEMA_AGENT_PROMPT` | prompts/templates.py | Agent 1 — structures raw DB metadata |
| `QUERY_AGENT_PROMPT` | prompts/templates.py | Agent 2 — extracts semantic key points |
| `SQL_GENERATOR_PROMPT` | prompts/templates.py | Agent 3 — first attempt |
| `SQL_RETRY_PROMPT` | prompts/templates.py | Agent 3 — retry with error context |
| `VALIDATOR_PROMPT` | prompts/templates.py | Agent 4 — LLM semantic check |

---

## Validation layers (Agent 4)

| Layer | Method | Catches |
|---|---|---|
| 1 | `validate_sql_syntax` tool (sqlglot) | Syntax errors, write operations |
| 2 | `validate_schema_refs` tool (sqlglot AST) | Unknown tables/columns |
| 2b | `run_explain` tool (psycopg2) | Planner-level errors (optional, needs live DB) |
| 3 | `VALIDATOR_PROMPT` + LLM | Semantic correctness vs the original question |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Your Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Model used for all agents |
| `DB_CONNECTION_STRING` | — | PostgreSQL DSN |
| `MAX_RETRIES` | `3` | Max Agent 3 retry attempts |
| `SCHEMA_CACHE_TTL_SECONDS` | `3600` | Schema cache lifetime (seconds) |
| `LOG_LEVEL` | `INFO` | INFO / DEBUG / WARNING |
