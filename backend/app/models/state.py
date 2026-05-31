from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    database_type: str
    database_config: Any
    sql: str
    intent: str
    confidence: float
    generated_sql: str
    explanation: str
    corrected_sql: str
    issues: list[str]
    optimization_tips: list[str]
    success: bool
    data: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    execution_time: float
    error: str | None
    answer: str
    examples: list[str]
    recommendations: list[str]
    retry_count: int
