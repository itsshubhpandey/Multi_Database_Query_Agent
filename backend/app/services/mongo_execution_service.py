from __future__ import annotations

import json
import time

from backend.app.config import get_settings
from backend.app.db.mongo import get_mongo_database
from backend.app.models.schemas import QueryExecutionResponse

try:
    from bson import json_util
except ImportError:  # pragma: no cover
    json_util = None


READ_OPERATIONS = {"find", "aggregate", "count_documents", "distinct"}
BLOCKED_AGGREGATION_STAGES = {"$out", "$merge"}


class MongoExecutionService:
    def execute(self, query: str, database_config=None) -> QueryExecutionResponse:
        started = time.perf_counter()
        try:
            command = _parse_command(query)
            operation = str(command.get("operation", "")).lower()
            if operation not in READ_OPERATIONS:
                raise ValueError(f"Only read operations are allowed: {', '.join(sorted(READ_OPERATIONS))}.")
            collection_name = str(command.get("collection", "")).strip()
            if not collection_name:
                raise ValueError("MongoDB command requires a collection name.")

            database = get_mongo_database(database_config)
            collection = database[collection_name]
            max_rows = get_settings().max_result_rows
            timeout_ms = get_settings().query_timeout_seconds * 1000

            if operation == "find":
                filter_value = _require_dict(command.get("filter", {}), "filter")
                projection = command.get("projection")
                if projection is not None:
                    projection = _require_dict(projection, "projection")
                cursor = collection.find(filter_value, projection).max_time_ms(timeout_ms)
                sort = command.get("sort", [])
                if sort:
                    cursor = cursor.sort(_normalize_sort(sort))
                limit = min(max(int(command.get("limit", max_rows)), 1), max_rows)
                rows = [_json_safe(item) for item in cursor.limit(limit)]
            elif operation == "aggregate":
                pipeline = command.get("pipeline", [])
                if not isinstance(pipeline, list):
                    raise ValueError("MongoDB aggregate pipeline must be a JSON array.")
                if any(isinstance(stage, dict) and BLOCKED_AGGREGATION_STAGES.intersection(stage) for stage in pipeline):
                    raise ValueError("$out and $merge aggregation stages are blocked.")
                rows = [_json_safe(item) for item in collection.aggregate(pipeline, maxTimeMS=timeout_ms)][:max_rows]
            elif operation == "count_documents":
                count = collection.count_documents(_require_dict(command.get("filter", {}), "filter"), maxTimeMS=timeout_ms)
                rows = [{"count": count}]
            else:
                field = str(command.get("field", "")).strip()
                if not field:
                    raise ValueError("MongoDB distinct command requires a field.")
                values = collection.distinct(field, _require_dict(command.get("filter", {}), "filter"), maxTimeMS=timeout_ms)
                rows = [{"value": _json_safe(value)} for value in values[:max_rows]]

            columns = list(dict.fromkeys(key for row in rows if isinstance(row, dict) for key in row))
            return QueryExecutionResponse(
                success=True,
                query=query,
                data=rows,
                columns=columns,
                row_count=len(rows),
                execution_time=round(time.perf_counter() - started, 4),
                database_type="mongodb",
            )
        except Exception as exc:
            return QueryExecutionResponse(
                success=False,
                query=query,
                error=str(exc),
                execution_time=round(time.perf_counter() - started, 4),
                database_type="mongodb",
            )


def _parse_command(query: str) -> dict:
    text = query.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    command = json.loads(text)
    if not isinstance(command, dict):
        raise ValueError("MongoDB query must be a JSON object.")
    return command


def _require_dict(value, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"MongoDB {name} must be a JSON object.")
    return value


def _normalize_sort(value) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        raise ValueError("MongoDB sort must be an array of [field, direction] pairs.")
    normalized: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or int(item[1]) not in {-1, 1}:
            raise ValueError("Each MongoDB sort entry must be [field, 1] or [field, -1].")
        normalized.append((str(item[0]), int(item[1])))
    return normalized


def _json_safe(value):
    if json_util is not None:
        return json.loads(json_util.dumps(value))
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
