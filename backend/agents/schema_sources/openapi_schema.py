"""
agents/schema_sources/openapi_schema.py
────────────────────────────────────────
Converts an OpenAPI 3.x spec (JSON or YAML) into a SchemaContext
so Agent 1 can work without a live database connection.

How it works:
  - Each top-level component schema → a TableInfo
  - Each schema property   → a ColumnInfo (type mapped to SQL type)
  - $ref relationships     → foreign key hints + relationships list
  - requestBody / response schemas are also extracted if not in components

Usage:
    from agents.schema_sources.openapi_schema import from_file, from_url, from_dict

    schema = from_file("openapi.yaml")
    schema = from_url("https://petstore3.swagger.io/api/v3/openapi.json")
    schema = from_dict(spec_dict)
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import structlog

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from state.graph_state import ColumnInfo, SchemaContext, TableInfo

log = structlog.get_logger()

# ── OpenAPI type → SQL type mapping ──────────────────────────────────────────

_TYPE_MAP: dict[tuple[str, str | None], str] = {
    ("string",  None):       "varchar",
    ("string",  "date"):     "date",
    ("string",  "date-time"):"timestamp",
    ("string",  "uuid"):     "uuid",
    ("string",  "email"):    "varchar",
    ("string",  "uri"):      "varchar",
    ("integer", None):       "integer",
    ("integer", "int32"):    "integer",
    ("integer", "int64"):    "bigint",
    ("number",  None):       "numeric",
    ("number",  "float"):    "real",
    ("number",  "double"):   "double precision",
    ("boolean", None):       "boolean",
    ("array",   None):       "jsonb",
    ("object",  None):       "jsonb",
}


def _sql_type(prop: dict[str, Any]) -> str:
    oa_type = prop.get("type", "string")
    fmt     = prop.get("format")
    return _TYPE_MAP.get((oa_type, fmt), _TYPE_MAP.get((oa_type, None), "varchar"))


def _to_snake(name: str) -> str:
    """PascalCase / camelCase → snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def _ref_to_table(ref: str) -> str:
    """'#/components/schemas/Order' → 'order'"""
    return _to_snake(ref.split("/")[-1])


# ── Core parser ───────────────────────────────────────────────────────────────

def from_dict(spec: dict[str, Any]) -> SchemaContext:
    """
    Parse an OpenAPI 3.x spec dict into a SchemaContext.
    Handles $ref resolution for component schemas.
    """
    schemas: dict[str, Any] = (
        spec.get("components", {}).get("schemas", {})
    )

    # Also harvest inline schemas from paths (requestBody / responses)
    _harvest_path_schemas(spec, schemas)

    tables: list[TableInfo] = []
    relationships: list[str] = []

    for schema_name, schema_def in schemas.items():
        table_name = _to_snake(schema_name)
        props = schema_def.get("properties", {})
        required_fields = set(schema_def.get("required", []))

        if not props:
            log.debug("openapi_schema_skip_no_props", name=schema_name)
            continue

        columns: list[ColumnInfo] = []

        for prop_name, prop_def in props.items():
            col_name  = _to_snake(prop_name)
            nullable  = prop_name not in required_fields

            # Detect $ref (foreign key)
            ref = prop_def.get("$ref") or prop_def.get("allOf", [{}])[0].get("$ref")
            if ref:
                ref_table = _ref_to_table(ref)
                fk_col    = f"{ref_table}_id"
                columns.append(ColumnInfo(
                    name=fk_col,
                    data_type="uuid",
                    nullable=nullable,
                    is_foreign_key=True,
                    references=f"{ref_table}.id",
                ))
                relationships.append(f"{table_name}.{fk_col} → {ref_table}.id")
                continue

            # Detect array of $refs
            if prop_def.get("type") == "array":
                items = prop_def.get("items", {})
                if "$ref" in items:
                    ref_table = _ref_to_table(items["$ref"])
                    relationships.append(f"{table_name}.id ←→ {ref_table} (many)")
                    continue

            # Detect primary key heuristic (name is "id" / ends in "_id" and is required)
            is_pk = col_name == "id" and prop_name in required_fields

            columns.append(ColumnInfo(
                name=col_name,
                data_type=_sql_type(prop_def),
                nullable=nullable,
                is_primary_key=is_pk,
            ))

        if columns:
            tables.append(TableInfo(name=table_name, columns=columns))
            log.debug("openapi_table_parsed", table=table_name, cols=len(columns))

    # De-duplicate relationships
    relationships = list(dict.fromkeys(relationships))

    log.info("openapi_schema_parsed", tables=len(tables), relationships=len(relationships))
    return SchemaContext(tables=tables, relationships=relationships)


def _harvest_path_schemas(spec: dict, schemas: dict) -> None:
    """
    Walk paths and add any inline requestBody / response schemas
    that aren't already in components/schemas.
    """
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if not isinstance(op, dict):
                continue
            # requestBody
            rb = op.get("requestBody", {})
            for media in rb.get("content", {}).values():
                s = media.get("schema", {})
                if s.get("type") == "object" and "properties" in s:
                    name = _path_to_name(path, method)
                    schemas.setdefault(name, s)
            # responses
            for status, resp in op.get("responses", {}).items():
                for media in resp.get("content", {}).values():
                    s = media.get("schema", {})
                    if s.get("type") == "object" and "properties" in s:
                        name = _path_to_name(path, method, status)
                        schemas.setdefault(name, s)


def _path_to_name(path: str, method: str, suffix: str = "") -> str:
    parts = [p for p in path.strip("/").split("/") if not p.startswith("{")]
    name  = "_".join(parts) or "resource"
    return f"{method}_{name}_{suffix}".strip("_") if suffix else f"{method}_{name}"


# ── File / URL loaders ────────────────────────────────────────────────────────

def from_file(path: str | Path) -> SchemaContext:
    """Load schema from a local .json or .yaml/.yml OpenAPI file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml
            spec = yaml.safe_load(text)
        except ImportError:
            raise ImportError("PyYAML is required for YAML files: pip install pyyaml")
    else:
        spec = json.loads(text)

    log.info("openapi_loaded_from_file", path=str(p))
    return from_dict(spec)


def from_url(url: str) -> SchemaContext:
    """Fetch and parse an OpenAPI spec from a URL."""
    with urllib.request.urlopen(url, timeout=15) as resp:
        content_type = resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8")

    if "yaml" in content_type or url.endswith((".yaml", ".yml")):
        try:
            import yaml
            spec = yaml.safe_load(body)
        except ImportError:
            raise ImportError("PyYAML is required for YAML specs: pip install pyyaml")
    else:
        spec = json.loads(body)

    log.info("openapi_loaded_from_url", url=url)
    return from_dict(spec)


def from_string(text: str, fmt: str = "json") -> SchemaContext:
    """Parse an OpenAPI spec from a string (json or yaml)."""
    if fmt == "yaml":
        import yaml
        spec = yaml.safe_load(text)
    else:
        spec = json.loads(text)
    return from_dict(spec)
