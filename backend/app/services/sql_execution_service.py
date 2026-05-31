from __future__ import annotations

import time

from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db.connection import get_connection, normalize_database_type
from backend.app.models.schemas import QueryExecutionResponse
from backend.app.utils.sql_safety import validate_sql_safety


class SqlExecutionService:
    def execute(self, sql: str, database_type: str = "postgresql", database_config=None) -> QueryExecutionResponse:
        normalized_db = normalize_database_type(database_type)
        safe, reason = validate_sql_safety(sql)
        if not safe:
            return QueryExecutionResponse(success=False, query=sql, error=reason, database_type=normalized_db)

        started = time.perf_counter()
        try:
            with get_connection(normalized_db, database_config) as connection:
                result = connection.execute(text(sql))
                if result.returns_rows:
                    rows = result.fetchmany(get_settings().max_result_rows)
                    columns = list(result.keys())
                    data = [dict(zip(columns, row)) for row in rows]
                    return QueryExecutionResponse(
                        success=True,
                        query=sql,
                        data=data,
                        columns=columns,
                        row_count=len(data),
                        execution_time=round(time.perf_counter() - started, 4),
                        database_type=normalized_db,
                    )
                connection.commit()
                return QueryExecutionResponse(
                    success=True,
                    query=sql,
                    data=[],
                    columns=[],
                    row_count=result.rowcount if result.rowcount and result.rowcount > 0 else 0,
                    execution_time=round(time.perf_counter() - started, 4),
                    database_type=normalized_db,
                )
        except Exception as exc:
            return QueryExecutionResponse(
                success=False,
                query=sql,
                error=str(exc),
                execution_time=round(time.perf_counter() - started, 4),
                database_type=normalized_db,
            )
