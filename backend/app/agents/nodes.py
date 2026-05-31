from __future__ import annotations

from backend.app.models.schemas import (
    ClassificationResult,
    DatabaseQaResult,
    SqlGenerationResult,
    SqlReviewResult,
)
from backend.app.models.state import AgentState
from backend.app.prompts.sql_prompts import (
    CLASSIFIER_PROMPT,
    DATABASE_QA_PROMPT,
    SQL_GENERATION_PROMPT,
    SQL_REVIEW_PROMPT,
)
from backend.app.services.ai_service import AiService
from backend.app.services.schema_service import SchemaService
from backend.app.services.sql_execution_service import SqlExecutionService
from backend.app.db.connection import normalize_database_type
from backend.app.utils.json_helpers import parse_json_object
from backend.app.utils.sql_safety import looks_like_sql

ai_service = AiService()
schema_service = SchemaService()
sql_execution_service = SqlExecutionService()


def user_query_classifier_node(state: AgentState) -> AgentState:
    user_input = state.get("user_input", "")
    fallback_intent = "sql_execution" if looks_like_sql(user_input) else "database_qa"
    response = ai_service.invoke(CLASSIFIER_PROMPT, user_input)
    parsed = parse_json_object(
        response,
        {"intent": fallback_intent, "confidence": 0.5, "user_input": user_input},
    )
    result = ClassificationResult(**parsed)
    return {**state, "intent": result.intent, "confidence": result.confidence, "user_input": result.user_input}


def english_to_sql_node(state: AgentState) -> AgentState:
    database_type = normalize_database_type(state.get("database_type"))
    schema = schema_service.as_prompt_context(
        database_type=database_type,
        database_config=state.get("database_config"),
    )
    prompt = SQL_GENERATION_PROMPT.format(schema=schema, dialect=dialect_name(database_type))
    response = ai_service.invoke(prompt, state.get("user_input", ""))
    parsed = parse_json_object(response, {"generated_sql": "", "explanation": response})
    result = SqlGenerationResult(**parsed)
    return {**state, "generated_sql": result.generated_sql, "sql": result.generated_sql, "explanation": result.explanation}


def sql_review_node(state: AgentState) -> AgentState:
    sql = state.get("sql") or state.get("generated_sql") or state.get("user_input", "")
    database_type = normalize_database_type(state.get("database_type"))
    prompt = SQL_REVIEW_PROMPT.format(error=state.get("error") or "None", dialect=dialect_name(database_type))
    response = ai_service.invoke(prompt, sql)
    parsed = parse_json_object(
        response,
        {"corrected_sql": sql, "issues": [], "optimization_tips": []},
    )
    result = SqlReviewResult(**parsed)
    corrected_sql = result.corrected_sql or sql
    return {
        **state,
        "sql": corrected_sql,
        "corrected_sql": corrected_sql,
        "issues": result.issues,
        "optimization_tips": result.optimization_tips,
    }


def sql_execution_node(state: AgentState) -> AgentState:
    database_type = normalize_database_type(state.get("database_type"))
    response = sql_execution_service.execute(
        state.get("sql") or state.get("user_input", ""),
        database_type=database_type,
        database_config=state.get("database_config"),
    )
    return {
        **state,
        "success": response.success,
        "data": response.data,
        "columns": response.columns,
        "row_count": response.row_count,
        "execution_time": response.execution_time,
        "error": response.error,
    }


def database_qa_node(state: AgentState) -> AgentState:
    database_type = normalize_database_type(state.get("database_type"))
    schema = schema_service.as_prompt_context(
        database_type=database_type,
        database_config=state.get("database_config"),
    )
    prompt = DATABASE_QA_PROMPT.format(schema=schema, dialect=dialect_name(database_type))
    response = ai_service.invoke(prompt, state.get("user_input", ""))
    parsed = parse_json_object(response, {"answer": response, "examples": [], "recommendations": []})
    result = DatabaseQaResult(**parsed)
    return {
        **state,
        "answer": result.answer,
        "examples": result.examples,
        "recommendations": result.recommendations,
        "success": True,
    }


def error_handler_node(state: AgentState) -> AgentState:
    retry_count = int(state.get("retry_count", 0)) + 1
    return {**state, "retry_count": retry_count}


def dialect_name(database_type: str) -> str:
    return "PostgreSQL" if normalize_database_type(database_type) == "postgresql" else "Microsoft SQL Server"
