from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from backend.app.agents.nodes import english_to_sql_node, schema_service, sql_review_node
from backend.app.db.connection import normalize_database_type
from backend.app.graph.workflow import sql_agent_graph
from backend.app.models.schemas import ChatRequest, ConnectionTestResponse, GenerateRequest, QueryRequest, ReviewRequest, SchemaRequest
from backend.app.orchestration import OrchestrationAgent
from backend.app.services.sql_execution_service import SqlExecutionService

router = APIRouter()
sql_execution_service = SqlExecutionService()
orchestration_agent = OrchestrationAgent()


@router.post("/query/execute")
async def execute_query(request: QueryRequest):
    return sql_execution_service.execute(
        request.query,
        database_type=request.database.type,
        database_config=request.database,
    )


@router.post("/query/review")
async def review_query(request: ReviewRequest):
    state = sql_review_node(
        {
            "user_input": request.query,
            "sql": request.query,
            "error": request.error,
            "database_type": request.database.type,
        }
    )
    return {
        "corrected_sql": state.get("corrected_sql", request.query),
        "issues": state.get("issues", []),
        "optimization_tips": state.get("optimization_tips", []),
    }


@router.post("/query/generate")
async def generate_query(request: GenerateRequest):
    state = _call_database_action(
        lambda: english_to_sql_node(
            {
                "user_input": request.question,
                "database_type": request.database.type,
                "database_config": request.database,
            }
        )
    )
    if request.execute:
        state = _call_database_action(
            lambda: sql_agent_graph.invoke(
                {
                    "user_input": request.question,
                    "intent": "english_to_sql",
                    "database_type": request.database.type,
                    "database_config": request.database,
                }
            )
        )
    return state


@router.post("/chat")
async def chat(request: ChatRequest):
    result = _call_database_action(lambda: orchestration_agent.handle(request))
    if request.stream:
        return StreamingResponse(_stream_orchestration_result(result), media_type="text/event-stream")
    return result


@router.get("/schema")
async def get_schema(database_type: str = "postgresql", force_refresh: bool = False):
    return _call_database_action(
        lambda: schema_service.get_schema(
            database_type=normalize_database_type(database_type),
            force_refresh=force_refresh,
        )
    )


@router.post("/schema")
async def post_schema(request: SchemaRequest):
    return _call_database_action(
        lambda: schema_service.get_schema(
            database_type=normalize_database_type(request.database.type),
            force_refresh=request.force_refresh,
            database_config=request.database,
        )
    )


@router.post("/connection/test", response_model=ConnectionTestResponse)
async def test_connection(request: SchemaRequest):
    schema = _call_database_action(
        lambda: schema_service.get_schema(
            database_type=request.database.type,
            force_refresh=True,
            database_config=request.database,
        )
    )
    database_label = {
        "postgresql": "PostgreSQL",
        "mssql": "Microsoft SQL Server",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
    }[request.database.type]
    return ConnectionTestResponse(
        success=True,
        database_type=request.database.type,
        message=f"Connected to {database_label}.",
        table_count=len(schema.tables),
    )


async def _stream_orchestration_result(result):
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    yield f"data: {json.dumps({'result': payload})}\n\n"
    yield "data: [DONE]\n\n"


def _call_database_action(action):
    try:
        return action()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Database connection failed. Check that the selected database is running, reachable, "
                "and that the .env connection URL or submitted connection settings are correct."
            ),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc
