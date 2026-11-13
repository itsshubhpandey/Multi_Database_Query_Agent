from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Intent = Literal[
    "sql_execution",
    "english_to_sql",
    "sql_debugging",
    "database_qa",
    "analytics_explanation",
    "schema_question",
]
DatabaseType = Literal["mssql", "postgresql", "mysql", "mongodb"]


class DatabaseSelection(BaseModel):
    type: DatabaseType = "postgresql"
    connection_uri: str = ""
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""
    driver: str = "ODBC Driver 17 for SQL Server"
    trust_server_certificate: bool = True
    auth_source: str = "admin"


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    database: DatabaseSelection = Field(default_factory=DatabaseSelection)


class GenerateRequest(BaseModel):
    question: str = Field(..., min_length=1)
    execute: bool = False
    database: DatabaseSelection = Field(default_factory=DatabaseSelection)


class ReviewRequest(BaseModel):
    query: str = Field(..., min_length=1)
    error: str | None = None
    database: DatabaseSelection = Field(default_factory=DatabaseSelection)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    stream: bool = False
    current_sql: str = ""
    approved_sql: str | None = None
    database: DatabaseSelection = Field(default_factory=DatabaseSelection)


class SchemaRequest(BaseModel):
    database: DatabaseSelection = Field(default_factory=DatabaseSelection)
    force_refresh: bool = False


class ConnectionTestResponse(BaseModel):
    success: bool
    database_type: DatabaseType
    message: str
    table_count: int = 0


class ClassificationResult(BaseModel):
    intent: Intent
    confidence: float = 0.0
    user_input: str


class SqlGenerationResult(BaseModel):
    generated_sql: str = ""
    explanation: str = ""


class SqlReviewResult(BaseModel):
    corrected_sql: str = ""
    issues: list[str] = Field(default_factory=list)
    optimization_tips: list[str] = Field(default_factory=list)


class QueryExecutionResponse(BaseModel):
    success: bool
    data: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0
    error: str | None = None
    query: str = ""
    database_type: DatabaseType = "postgresql"


class DatabaseQaResult(BaseModel):
    answer: str = ""
    examples: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SchemaColumn(BaseModel):
    name: str
    type: str
    nullable: bool


class SchemaTable(BaseModel):
    schema_name: str
    table_name: str
    columns: list[SchemaColumn] = Field(default_factory=list)


class SchemaResponse(BaseModel):
    tables: list[SchemaTable] = Field(default_factory=list)
    cached: bool = False
    database_type: DatabaseType = "postgresql"


class ToolTrace(BaseModel):
    name: str
    endpoint: str
    status: Literal["completed", "failed"] = "completed"


class OrchestrationResponse(BaseModel):
    success: bool = True
    intent: str
    message: str
    tools: list[ToolTrace] = Field(default_factory=list)
    sql: str = ""
    approval_required: bool = False
    result: QueryExecutionResponse | None = None
    database_schema: SchemaResponse | None = None
