from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from backend.app.agents.nodes import dialect_name, english_to_sql_node, schema_service, sql_review_node
from backend.app.models.schemas import DatabaseSelection, QueryExecutionResponse, SchemaResponse
from backend.app.prompts.sql_prompts import DATABASE_QA_PROMPT
from backend.app.services.ai_service import AiService
from backend.app.services.sql_execution_service import SqlExecutionService
from backend.app.utils.json_helpers import parse_json_object


class AgentToolbox:
    """Internal tool adapters backed by the same services as the public API."""

    endpoints = {
        "generate_sql": "/api/query/generate",
        "review_sql": "/api/query/review",
        "execute_sql": "/api/query/execute",
        "get_schema": "/api/schema",
        "answer_database_question": "/api/chat",
    }

    def __init__(self) -> None:
        self._execution_service = SqlExecutionService()
        self._ai_service = AiService()

    def generate_sql(self, question: str, database: DatabaseSelection) -> dict:
        state = english_to_sql_node(
            {
                "user_input": question,
                "database_type": database.type,
                "database_config": database,
            }
        )
        return {
            "sql": state.get("generated_sql") or state.get("sql") or "",
            "explanation": state.get("explanation", ""),
        }

    def review_sql(self, sql: str, database: DatabaseSelection, error: str | None = None) -> dict:
        state = sql_review_node(
            {
                "user_input": sql,
                "sql": sql,
                "error": error,
                "database_type": database.type,
            }
        )
        return {
            "sql": state.get("corrected_sql") or state.get("sql") or sql,
            "issues": state.get("issues", []),
            "optimization_tips": state.get("optimization_tips", []),
        }

    def execute_sql(self, sql: str, database: DatabaseSelection) -> QueryExecutionResponse:
        return self._execution_service.execute(
            sql,
            database_type=database.type,
            database_config=database,
        )

    def get_schema(self, database: DatabaseSelection, force_refresh: bool = False) -> SchemaResponse:
        return schema_service.get_schema(
            database_type=database.type,
            force_refresh=force_refresh,
            database_config=database,
        )

    def answer_database_question(self, question: str, database: DatabaseSelection) -> str:
        try:
            schema = schema_service.as_prompt_context(
                database_type=database.type,
                database_config=database,
            )
        except (RuntimeError, SQLAlchemyError):
            schema = "No connected schema is required for this conceptual question."
        prompt = DATABASE_QA_PROMPT.format(schema=schema, dialect=dialect_name(database.type))
        response = self._ai_service.invoke(prompt, question)
        return str(parse_json_object(response, {"answer": response}).get("answer", response))
