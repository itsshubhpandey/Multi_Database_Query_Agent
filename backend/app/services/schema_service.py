from __future__ import annotations

import time

from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db.connection import get_connection, normalize_database_type
from backend.app.db.mongo import get_mongo_database
from backend.app.models.schemas import SchemaColumn, SchemaResponse, SchemaTable


class SchemaService:
    def __init__(self) -> None:
        self._cache: dict[str, SchemaResponse] = {}
        self._cache_time: dict[str, float] = {}

    def get_schema(self, database_type: str = "postgresql", force_refresh: bool = False, database_config=None) -> SchemaResponse:
        normalized_db = normalize_database_type(database_type)
        use_cache = database_config is None
        ttl = get_settings().schema_cache_seconds
        now = time.time()
        if (
            use_cache
            and
            normalized_db in self._cache
            and not force_refresh
            and now - self._cache_time.get(normalized_db, 0.0) < ttl
        ):
            cached_schema = self._cache[normalized_db]
            cached_schema.cached = True
            return cached_schema

        query = self._schema_query(normalized_db)
        if normalized_db == "mongodb":
            response = self._get_mongo_schema(database_config)
            if use_cache:
                self._cache[normalized_db] = response
                self._cache_time[normalized_db] = now
            return response

        tables: dict[tuple[str, str], SchemaTable] = {}
        with get_connection(normalized_db, database_config) as connection:
            for row in connection.execute(query):
                schema_name = row.TABLE_SCHEMA
                table_name = row.TABLE_NAME
                key = (schema_name, table_name)
                if key not in tables:
                    tables[key] = SchemaTable(schema_name=schema_name, table_name=table_name)
                tables[key].columns.append(
                    SchemaColumn(
                        name=row.COLUMN_NAME,
                        type=row.DATA_TYPE,
                        nullable=str(row.IS_NULLABLE).upper() == "YES",
                    )
                )

        response = SchemaResponse(tables=list(tables.values()), cached=False, database_type=normalized_db)
        if use_cache:
            self._cache[normalized_db] = response
            self._cache_time[normalized_db] = now
        return response

    def as_prompt_context(self, database_type: str = "postgresql", database_config=None) -> str:
        schema = self.get_schema(database_type=database_type, database_config=database_config)
        lines: list[str] = []
        for table in schema.tables[:80]:
            columns = ", ".join(f"{column.name} {column.type}" for column in table.columns[:40])
            lines.append(f"{table.schema_name}.{table.table_name}({columns})")
        return "\n".join(lines) or "No schema available."

    @staticmethod
    def _schema_query(database_type: str):
        if database_type == "postgresql":
            return text(
                """
                SELECT table_schema AS "TABLE_SCHEMA",
                       table_name AS "TABLE_NAME",
                       column_name AS "COLUMN_NAME",
                       data_type AS "DATA_TYPE",
                       is_nullable AS "IS_NULLABLE"
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
                """
            )
        if database_type == "mysql":
            return text(
                """
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """
            )
        return text(
            """
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """
        )

    @staticmethod
    def _get_mongo_schema(database_config=None) -> SchemaResponse:
        database = get_mongo_database(database_config)
        tables: list[SchemaTable] = []
        for collection_name in sorted(database.list_collection_names()):
            field_types: dict[str, set[str]] = {}
            documents = list(database[collection_name].find({}).limit(20))
            for document in documents:
                for field, value in document.items():
                    field_types.setdefault(field, set()).add(_mongo_type_name(value))
            columns = [
                SchemaColumn(
                    name=field,
                    type=" | ".join(sorted(types)),
                    nullable=any(field not in document for document in documents),
                )
                for field, types in sorted(field_types.items())
            ]
            tables.append(
                SchemaTable(
                    schema_name=database.name,
                    table_name=collection_name,
                    columns=columns,
                )
            )
        return SchemaResponse(tables=tables, cached=False, database_type="mongodb")


def _mongo_type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__
