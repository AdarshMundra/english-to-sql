"""
tests/test_pipeline.py  (Phase 7)
───────────────────────────────────
Unit + integration tests for the LangChain + LangGraph text-to-SQL pipeline.

Run:
    pytest tests/ -v
    pytest tests/ -v -k "TestValidator"
    pytest tests/ -v -k "TestGraph"
"""

from __future__ import annotations

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from state.graph_state import (
    GraphState, SchemaContext, TableInfo, ColumnInfo, QueryKeyPoints,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_schema() -> SchemaContext:
    return SchemaContext(
        tables=[
            TableInfo(
                name="customers",
                row_count=5000,
                columns=[
                    ColumnInfo(name="id", data_type="uuid", nullable=False, is_primary_key=True),
                    ColumnInfo(name="name", data_type="varchar", nullable=False),
                    ColumnInfo(name="city", data_type="varchar", nullable=True),
                    ColumnInfo(name="created_at", data_type="timestamp", nullable=False),
                ],
            ),
            TableInfo(
                name="orders",
                row_count=42000,
                columns=[
                    ColumnInfo(name="id", data_type="uuid", nullable=False, is_primary_key=True),
                    ColumnInfo(name="customer_id", data_type="uuid", nullable=False,
                               is_foreign_key=True, references="customers.id"),
                    ColumnInfo(name="total_value", data_type="numeric", nullable=False),
                    ColumnInfo(name="created_at", data_type="timestamp", nullable=False),
                ],
            ),
            TableInfo(
                name="products",
                row_count=1200,
                columns=[
                    ColumnInfo(name="id", data_type="uuid", nullable=False, is_primary_key=True),
                    ColumnInfo(name="name", data_type="varchar", nullable=False),
                    ColumnInfo(name="category", data_type="varchar", nullable=True),
                    ColumnInfo(name="stock_quantity", data_type="integer", nullable=False),
                ],
            ),
        ],
        relationships=["orders.customer_id → customers.id"],
    )


@pytest.fixture
def sample_key_points() -> QueryKeyPoints:
    return QueryKeyPoints(
        intent="count",
        tables_hint=["orders", "customers"],
        filters=["customers.city = Mumbai", "last month"],
        aggregations=["COUNT(*)"],
        raw_query="How many orders from Mumbai last month?",
    )


@pytest.fixture
def base_state(sample_schema, sample_key_points) -> GraphState:
    return {
        "english_query": "How many orders from Mumbai last month?",
        "connection_string": "",
        "schema_context": sample_schema,
        "query_key_points": sample_key_points,
        "generated_sql": None,
        "validation_passed": False,
        "validation_error": None,
        "final_sql": None,
        "retry_count": 0,
        "max_retries": 3,
        "status": "running",
        "metadata": {},
    }


# ── Prompt Templates ──────────────────────────────────────────────────────────

class TestPromptTemplates:
    def test_schema_prompt_has_required_variable(self):
        from prompts.templates import SCHEMA_AGENT_PROMPT
        vars_ = SCHEMA_AGENT_PROMPT.input_variables
        assert "raw_schema_json" in vars_

    def test_query_prompt_has_required_variable(self):
        from prompts.templates import QUERY_AGENT_PROMPT
        vars_ = QUERY_AGENT_PROMPT.input_variables
        assert "english_query" in vars_

    def test_sql_generator_prompt_variables(self):
        from prompts.templates import SQL_GENERATOR_PROMPT
        vars_ = SQL_GENERATOR_PROMPT.input_variables
        assert "schema_summary" in vars_
        assert "raw_query" in vars_
        assert "key_points_json" in vars_

    def test_sql_retry_prompt_variables(self):
        from prompts.templates import SQL_RETRY_PROMPT
        vars_ = SQL_RETRY_PROMPT.input_variables
        assert "previous_sql" in vars_
        assert "error_message" in vars_

    def test_validator_prompt_variables(self):
        from prompts.templates import VALIDATOR_PROMPT
        vars_ = VALIDATOR_PROMPT.input_variables
        assert "schema_summary" in vars_
        assert "generated_sql" in vars_

    def test_schema_prompt_formats_correctly(self):
        from prompts.templates import SCHEMA_AGENT_PROMPT
        msgs = SCHEMA_AGENT_PROMPT.format_messages(raw_schema_json='{"tables": []}')
        assert len(msgs) == 2   # system + human

    def test_query_prompt_formats_correctly(self):
        from prompts.templates import QUERY_AGENT_PROMPT
        msgs = QUERY_AGENT_PROMPT.format_messages(english_query="test query")
        assert any("test query" in str(m.content) for m in msgs)


# ── Tools ─────────────────────────────────────────────────────────────────────

class TestTools:
    def test_validate_sql_syntax_valid_select(self):
        from tools.db_tools import validate_sql_syntax
        result = json.loads(validate_sql_syntax.invoke({"sql": "SELECT id FROM customers"}))
        assert result["valid"] is True

    def test_validate_sql_syntax_rejects_insert(self):
        from tools.db_tools import validate_sql_syntax
        result = json.loads(validate_sql_syntax.invoke({"sql": "INSERT INTO t (a) VALUES (1)"}))
        assert result["valid"] is False
        assert "INSERT" in result["error"]

    def test_validate_sql_syntax_rejects_drop(self):
        from tools.db_tools import validate_sql_syntax
        result = json.loads(validate_sql_syntax.invoke({"sql": "DROP TABLE customers"}))
        assert result["valid"] is False

    def test_validate_sql_syntax_catches_parse_error(self):
        from tools.db_tools import validate_sql_syntax
        result = json.loads(validate_sql_syntax.invoke({"sql": "SELECT FROM WHERE HAVING"}))
        assert result["valid"] is False
        assert "Syntax" in result["error"] or "error" in result["error"].lower()

    def test_validate_schema_refs_known_table(self, sample_schema):
        from tools.db_tools import validate_schema_refs
        schema_json = json.dumps({
            "tables": [
                {"name": t.name, "columns": [col.model_dump() for col in t.columns]}
                for t in sample_schema.tables
            ]
        })
        result = json.loads(validate_schema_refs.invoke({
            "sql": "SELECT id, name FROM customers",
            "schema_json": schema_json,
        }))
        assert result["valid"] is True

    def test_validate_schema_refs_unknown_table(self, sample_schema):
        from tools.db_tools import validate_schema_refs
        schema_json = json.dumps({
            "tables": [
                {"name": t.name, "columns": [col.model_dump() for col in t.columns]}
                for t in sample_schema.tables
            ]
        })
        result = json.loads(validate_schema_refs.invoke({
            "sql": "SELECT * FROM invoices",
            "schema_json": schema_json,
        }))
        assert result["valid"] is False
        assert "invoices" in result["error"]

    def test_tools_are_langchain_tools(self):
        from tools.db_tools import validate_sql_syntax, validate_schema_refs
        from langchain_core.tools import BaseTool
        assert isinstance(validate_sql_syntax, BaseTool)
        assert isinstance(validate_schema_refs, BaseTool)


# ── SQL Generator Node ────────────────────────────────────────────────────────

class TestSQLGeneratorNode:
    def test_schema_to_summary_contains_tables(self, sample_schema):
        from agents.sql_generator import _schema_to_summary
        summary = _schema_to_summary(sample_schema)
        assert "customers" in summary
        assert "orders" in summary

    def test_schema_to_summary_shows_fk(self, sample_schema):
        from agents.sql_generator import _schema_to_summary
        summary = _schema_to_summary(sample_schema)
        assert "FK→" in summary

    def test_strip_fences_removes_markdown(self):
        from agents.sql_generator import _strip_fences
        raw = "```sql\nSELECT 1\n```"
        assert _strip_fences(raw) == "SELECT 1"

    def test_strip_fences_passthrough(self):
        from agents.sql_generator import _strip_fences
        assert _strip_fences("SELECT 1") == "SELECT 1"

    @patch("agents.sql_generator.ChatOpenAI")
    def test_node_returns_generated_sql(self, MockLLM, base_state):
        mock_chain_result = "SELECT COUNT(*) FROM orders o JOIN customers c ON o.customer_id = c.id"
        mock_llm_instance = MagicMock()
        MockLLM.return_value = mock_llm_instance

        # Mock the chain: prompt | llm | parser
        with patch("agents.sql_generator._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = mock_chain_result
            mock_build.return_value = mock_chain

            from agents.sql_generator import sql_generator_node
            result = sql_generator_node(base_state)

        assert "generated_sql" in result
        assert "SELECT" in result["generated_sql"].upper()
        assert result["retry_count"] == 1

    @patch("agents.sql_generator._build_chain")
    def test_retry_increments_count(self, mock_build, base_state):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "SELECT 1"
        mock_build.return_value = mock_chain

        state_with_error = {**base_state, "retry_count": 1, "validation_error": "unknown table"}

        from agents.sql_generator import sql_generator_node
        result = sql_generator_node(state_with_error)
        assert result["retry_count"] == 2


# ── Validator Node ────────────────────────────────────────────────────────────

class TestValidatorNode:
    @patch("agents.validator._build_semantic_chain")
    def test_passes_valid_select(self, mock_chain_builder, base_state):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = {"valid": True, "error_message": None}
        mock_chain_builder.return_value = mock_chain

        state = {**base_state, "generated_sql": "SELECT COUNT(*) FROM orders"}
        from agents.validator import validator_node
        result = validator_node(state)
        assert result["validation_passed"] is True
        assert result["final_sql"] == "SELECT COUNT(*) FROM orders"

    def test_rejects_write_op_without_llm(self, base_state):
        state = {**base_state, "generated_sql": "DELETE FROM customers"}
        from agents.validator import validator_node
        result = validator_node(state)
        assert result["validation_passed"] is False
        assert "DELETE" in result["validation_error"]

    def test_rejects_unknown_table_without_llm(self, base_state):
        state = {**base_state, "generated_sql": "SELECT * FROM nonexistent_table"}
        from agents.validator import validator_node
        result = validator_node(state)
        assert result["validation_passed"] is False

    @patch("agents.validator._build_semantic_chain")
    def test_fails_on_llm_semantic_error(self, mock_chain_builder, base_state):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = {
            "valid": False, "error_message": "Query returns wrong columns"
        }
        mock_chain_builder.return_value = mock_chain

        state = {**base_state, "generated_sql": "SELECT id FROM orders"}
        from agents.validator import validator_node
        result = validator_node(state)
        assert result["validation_passed"] is False
        assert "wrong columns" in result["validation_error"]


# ── Graph Routing ─────────────────────────────────────────────────────────────

class TestGraphRouting:
    def test_should_retry_when_validation_fails_and_retries_left(self, base_state):
        from graph.pipeline_graph import should_retry
        state = {**base_state, "validation_passed": False, "retry_count": 1, "max_retries": 3}
        assert should_retry(state) == "sql_generator"

    def test_should_end_when_validation_passes(self, base_state):
        from graph.pipeline_graph import should_retry
        state = {**base_state, "validation_passed": True, "retry_count": 1}
        assert should_retry(state) == "end"

    def test_should_end_when_retries_exhausted(self, base_state):
        from graph.pipeline_graph import should_retry
        state = {**base_state, "validation_passed": False, "retry_count": 3, "max_retries": 3}
        assert should_retry(state) == "end"

    def test_graph_compiles(self):
        from graph.pipeline_graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        from graph.pipeline_graph import build_graph
        graph = build_graph()
        node_names = set(graph.nodes.keys())
        assert "schema_agent" in node_names
        assert "query_agent" in node_names
        assert "sql_generator" in node_names
        assert "validator" in node_names


# ── End-to-end with mocked LLM ───────────────────────────────────────────────

class TestEndToEnd:
    @patch("agents.validator._build_semantic_chain")
    @patch("agents.sql_generator._build_chain")
    @patch("agents.query_agent._build_chain")
    def test_full_pipeline_success(
        self, mock_query_chain_fn, mock_gen_chain_fn, mock_val_chain_fn,
        sample_schema, sample_key_points
    ):
        # Mock query agent chain
        mock_query_chain = MagicMock()
        mock_query_chain.invoke.return_value = sample_key_points.model_dump()
        mock_query_chain_fn.return_value = mock_query_chain

        # Mock SQL generator chain
        mock_gen_chain = MagicMock()
        mock_gen_chain.invoke.return_value = "SELECT COUNT(*) FROM orders"
        mock_gen_chain_fn.return_value = mock_gen_chain

        # Mock validator LLM chain
        mock_val_chain = MagicMock()
        mock_val_chain.invoke.return_value = {"valid": True, "error_message": None}
        mock_val_chain_fn.return_value = mock_val_chain

        from run import run_pipeline
        result = run_pipeline(
            english_query="How many orders?",
            schema_context=sample_schema,
        )

        assert result["status"] == "success"
        assert result["sql"] is not None
        assert result["attempts"] >= 1

    @patch("agents.validator._build_semantic_chain")
    @patch("agents.sql_generator._build_chain")
    @patch("agents.query_agent._build_chain")
    def test_pipeline_fails_after_max_retries(
        self, mock_query_chain_fn, mock_gen_chain_fn, mock_val_chain_fn,
        sample_schema, sample_key_points
    ):
        mock_query_chain = MagicMock()
        mock_query_chain.invoke.return_value = sample_key_points.model_dump()
        mock_query_chain_fn.return_value = mock_query_chain

        # Always return SQL with an unknown table (will fail schema ref check)
        mock_gen_chain = MagicMock()
        mock_gen_chain.invoke.return_value = "SELECT * FROM ghost_table"
        mock_gen_chain_fn.return_value = mock_gen_chain

        mock_val_chain = MagicMock()
        mock_val_chain.invoke.return_value = {"valid": True}
        mock_val_chain_fn.return_value = mock_val_chain

        from run import run_pipeline
        result = run_pipeline(
            english_query="show ghost data",
            schema_context=sample_schema,
            max_retries=2,
        )

        assert result["status"] == "failed"
        assert result["attempts"] >= 2


# ── Benchmark: known-good SQL through validator ───────────────────────────────

BENCHMARK = [
    (
        "Show all customers from Delhi",
        "SELECT id, name, city FROM customers WHERE city = 'Delhi'",
    ),
    (
        "How many products are out of stock?",
        "SELECT COUNT(*) FROM products WHERE stock_quantity = 0",
    ),
    (
        "Top 10 customers by total order value",
        "SELECT c.name, SUM(o.total_value) AS total FROM customers c "
        "JOIN orders o ON o.customer_id = c.id GROUP BY c.name ORDER BY total DESC LIMIT 10",
    ),
    (
        "How many orders were placed last month?",
        "SELECT COUNT(*) FROM orders WHERE created_at >= date_trunc('month', now() - interval '1 month') "
        "AND created_at < date_trunc('month', now())",
    ),
]


class TestBenchmark:
    @pytest.mark.parametrize("query,sql", BENCHMARK)
    def test_known_good_sql_passes_programmatic_validation(self, query, sql, sample_schema):
        """
        Ensures the programmatic layers (syntax + schema refs) pass for
        hand-verified correct SQL. LLM layer is not invoked.
        """
        from tools.db_tools import validate_sql_syntax, validate_schema_refs

        r1 = json.loads(validate_sql_syntax.invoke({"sql": sql}))
        assert r1["valid"], f"Syntax fail for '{query}': {r1.get('error')}"

        schema_json = json.dumps({
            "tables": [
                {"name": t.name, "columns": [col.model_dump() for col in t.columns]}
                for t in sample_schema.tables
            ]
        })
        r2 = json.loads(validate_schema_refs.invoke({"sql": sql, "schema_json": schema_json}))
        assert r2["valid"], f"Schema ref fail for '{query}': {r2.get('error')}"


# ── Agent 5: Executor ─────────────────────────────────────────────────────────

class TestExecutorAgent:
    def test_skips_when_execute_query_false(self, base_state):
        from agents.executor_agent import executor_agent_node
        state = {**base_state, "execute_query": False, "validation_passed": True,
                 "final_sql": "SELECT 1"}
        result = executor_agent_node(state)
        assert result == {}

    def test_skips_when_validation_not_passed(self, base_state):
        from agents.executor_agent import executor_agent_node
        state = {**base_state, "execute_query": True, "validation_passed": False,
                 "final_sql": "SELECT 1",
                 "connection_string": "postgresql://x:x@localhost/x"}
        result = executor_agent_node(state)
        assert result["query_result"].error is not None

    def test_skips_when_no_connection(self, base_state):
        import os
        from agents.executor_agent import executor_agent_node
        env_backup = os.environ.pop("DB_CONNECTION_STRING", None)
        state = {**base_state, "execute_query": True, "validation_passed": True,
                 "final_sql": "SELECT 1", "connection_string": ""}
        result = executor_agent_node(state)
        assert result["query_result"].error is not None
        if env_backup:
            os.environ["DB_CONNECTION_STRING"] = env_backup

    def test_skips_when_no_sql(self, base_state):
        from agents.executor_agent import executor_agent_node
        state = {**base_state, "execute_query": True, "validation_passed": True,
                 "final_sql": None, "generated_sql": None,
                 "connection_string": "postgresql://x:x@localhost/x"}
        result = executor_agent_node(state)
        assert result["query_result"].error is not None


class TestExecuteSqlTool:
    def test_rejects_insert(self):
        from tools.db_tools import execute_sql
        import json
        r = json.loads(execute_sql.invoke({
            "sql": "INSERT INTO students VALUES (1)",
            "connection_string": "postgresql://x:x@localhost/test",
            "max_rows": 10,
        }))
        assert r["error"] is not None
        assert "SELECT" in r["error"]

    def test_rejects_delete(self):
        from tools.db_tools import execute_sql
        import json
        r = json.loads(execute_sql.invoke({
            "sql": "DELETE FROM students",
            "connection_string": "postgresql://x:x@localhost/test",
            "max_rows": 10,
        }))
        assert r["error"] is not None


class TestQueryResultModel:
    def test_default_values(self):
        from state.graph_state import QueryResult
        qr = QueryResult()
        assert qr.columns == []
        assert qr.rows == []
        assert qr.row_count == 0
        assert qr.truncated is False
        assert qr.error is None

    def test_with_data(self):
        from state.graph_state import QueryResult
        qr = QueryResult(
            columns=["name", "cgpa"],
            rows=[["Sneha Patel", 9.1], ["Arjun Sharma", 8.75]],
            row_count=2,
            execution_time_ms=12.5,
        )
        assert qr.row_count == 2
        assert qr.columns[0] == "name"
