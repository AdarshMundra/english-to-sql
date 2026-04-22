"""
tools/db_tools.py
─────────────────
LangChain @tool definitions used by the agent nodes.

Tools:
  fetch_db_schema   — pulls raw metadata from PostgreSQL
  validate_sql_syntax   — sqlglot syntax + write-guard check
  validate_schema_refs  — checks all table/column refs exist in SchemaContext
  run_explain           — optional live EXPLAIN dry-run
"""

import json
import re
from typing import Any
from urllib.parse import quote, unquote, urlparse, urlunparse

import sqlglot
import sqlglot.errors
from langchain_core.tools import tool


def _sanitize_dsn(dsn: str) -> str:
    """Re-encode the password in a PostgreSQL DSN so special chars like % or @ are safe."""
    try:
        parsed = urlparse(dsn)
        if parsed.password is not None:
            # urlparse splits at the last @ so passwords with @ are handled correctly.
            # parsed.password already percent-decodes, so re-encode cleanly.
            user = quote(parsed.username or "", safe="")
            pwd  = quote(parsed.password, safe="")
            netloc = f"{user}:{pwd}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return dsn


# ── Write-op guard ─────────────────────────────────────────────────────────────

_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


# ── Tool: fetch raw schema from PostgreSQL ─────────────────────────────────────

@tool
def fetch_db_schema(connection_string: str) -> str:
    """
    Connect to a PostgreSQL database and return raw schema metadata as a JSON string.
    Includes tables, columns (with types, nullability, PK/FK flags), and row counts.
    """
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError("psycopg2 is required. Run: pip install psycopg2-binary")

    conn = psycopg2.connect(_sanitize_dsn(connection_string))
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.table_name, ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                  ON tc.constraint_name = ku.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
            ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
            WHERE c.table_schema = 'public'
            ORDER BY c.table_name, c.ordinal_position
        """)
        columns = cur.fetchall()

        cur.execute("""
            SELECT kcu.table_name, kcu.column_name,
                   ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
        """)
        fkeys = {(r[0], r[1]): f"{r[2]}.{r[3]}" for r in cur.fetchall()}

        cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public'")
        row_counts = {r[0]: r[1] for r in cur.fetchall()}
        cur.close()
    finally:
        conn.close()

    raw: dict[str, Any] = {"tables": {}, "foreign_keys": []}
    for row in columns:
        table, col, dtype, nullable, is_pk = row
        if table not in raw["tables"]:
            raw["tables"][table] = {"columns": [], "row_count": row_counts.get(table)}
        fk_ref = fkeys.get((table, col))
        raw["tables"][table]["columns"].append({
            "name": col,
            "data_type": dtype,
            "nullable": nullable == "YES",
            "is_primary_key": bool(is_pk),
            "is_foreign_key": fk_ref is not None,
            "references": fk_ref,
        })
        if fk_ref:
            raw["foreign_keys"].append(f"{table}.{col} → {fk_ref}")

    return json.dumps(raw, indent=2)


# ── Tool: programmatic syntax + write-guard validation ─────────────────────────

@tool
def validate_sql_syntax(sql: str) -> str:
    """
    Check a SQL string for:
      1. Write operations (INSERT/UPDATE/DELETE/DROP etc.) — always rejected
      2. Syntax errors via sqlglot PostgreSQL parser

    Returns JSON: {"valid": true} or {"valid": false, "error": "..."}
    """
    # Write-op guard
    m = _WRITE_RE.search(sql)
    if m:
        return json.dumps({
            "valid": False,
            "error": f"Write operation '{m.group()}' is not permitted. Only SELECT is allowed."
        })

    # Syntax check
    try:
        sqlglot.parse_one(sql, dialect="postgres")
        return json.dumps({"valid": True})
    except sqlglot.errors.ParseError as exc:
        return json.dumps({"valid": False, "error": f"Syntax error: {exc}"})


# ── Tool: schema reference validation ──────────────────────────────────────────

@tool
def validate_schema_refs(sql: str, schema_json: str) -> str:
    """
    Parse the SQL AST and verify every referenced table and column exists
    in the provided schema JSON (the output of the schema agent).

    Returns JSON: {"valid": true} or {"valid": false, "error": "..."}
    """
    try:
        schema = json.loads(schema_json)
    except json.JSONDecodeError:
        return json.dumps({"valid": False, "error": "Could not parse schema JSON"})

    known_tables = {t["name"].lower() for t in schema.get("tables", [])}
    known_columns: set[str] = set()
    for t in schema.get("tables", []):
        for col in t.get("columns", []):
            known_columns.add(col["name"].lower())

    try:
        ast = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        return json.dumps({"valid": False, "error": f"Cannot parse SQL for ref check: {exc}"})

    ref_tables: set[str] = set()
    ref_columns: set[str] = set()
    for node in ast.walk():
        if isinstance(node, sqlglot.exp.Table) and node.name:
            ref_tables.add(node.name.lower())
        elif isinstance(node, sqlglot.exp.Column) and node.name:
            ref_columns.add(node.name.lower())

    unknown_tables = ref_tables - known_tables - {""}
    if unknown_tables:
        return json.dumps({
            "valid": False,
            "error": f"Unknown table(s) not in schema: {', '.join(sorted(unknown_tables))}"
        })

    unknown_cols = ref_columns - known_columns - {"*", ""}
    if unknown_cols:
        return json.dumps({
            "valid": False,
            "error": f"Unknown column(s) not in schema: {', '.join(sorted(unknown_cols))}"
        })

    return json.dumps({"valid": True})


# ── Tool: EXPLAIN dry-run ──────────────────────────────────────────────────────

@tool
def run_explain(sql: str, connection_string: str) -> str:
    """
    Run EXPLAIN (without ANALYZE) on the SQL against a live PostgreSQL database.
    Catches semantic errors (wrong join paths, type mismatches) the parser can't catch.

    Returns JSON: {"valid": true} or {"valid": false, "error": "..."}
    """
    try:
        import psycopg2
        conn = psycopg2.connect(_sanitize_dsn(connection_string))
        cur = conn.cursor()
        cur.execute(f"EXPLAIN {sql}")
        cur.close()
        conn.close()
        return json.dumps({"valid": True})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"valid": False, "error": str(exc)})


# ── Tool: execute a validated SQL SELECT against a live DB ────────────────────

@tool
def execute_sql(sql: str, connection_string: str, max_rows: int = 500) -> str:
    """
    Execute a validated SQL SELECT statement against a PostgreSQL database.
    Returns results as a JSON string with columns, rows, row_count,
    truncated flag, and execution_time_ms.
    Only SELECT statements are permitted — any other statement raises an error.
    """
    import time as _time
    import re as _re

    if _re.search(r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b',
                  sql, _re.IGNORECASE):
        return json.dumps({"error": "Only SELECT statements are permitted."})

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return json.dumps({"error": "psycopg2 not installed. Run: pip install psycopg2-binary"})

    t0 = _time.perf_counter()
    try:
        conn = psycopg2.connect(_sanitize_dsn(connection_string))
        conn.set_session(readonly=True, autocommit=True)   # read-only session
        cur = conn.cursor()
        cur.execute(sql)

        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)   # fetch one extra to detect truncation
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        # Convert to JSON-serialisable types
        def _serialise(v: Any) -> Any:
            if v is None:
                return None
            if isinstance(v, (int, float, bool, str)):
                return v
            from decimal import Decimal
            from datetime import date, datetime, time
            if isinstance(v, Decimal):
                return float(v)
            if isinstance(v, (datetime, date, time)):
                return str(v)
            return str(v)

        serialised_rows = [[_serialise(cell) for cell in row] for row in rows]
        elapsed_ms = round((_time.perf_counter() - t0) * 1000, 2)

        cur.close()
        conn.close()

        return json.dumps({
            "columns": columns,
            "rows": serialised_rows,
            "row_count": len(serialised_rows),
            "truncated": truncated,
            "execution_time_ms": elapsed_ms,
            "error": None,
        })

    except Exception as exc:
        elapsed_ms = round((_time.perf_counter() - t0) * 1000, 2)
        return json.dumps({
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "execution_time_ms": elapsed_ms,
            "error": str(exc),
        })
