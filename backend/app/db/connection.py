from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from typing import Iterator
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError

from backend.app.config import get_settings

_engines: dict[str, Engine] = {}


def get_database_url(database_type: str, database_config=None) -> str:
    settings = get_settings()
    normalized = normalize_database_type(database_type)
    if normalized == "postgresql":
        return _with_postgres_ssl(settings.postgres_url)
    dynamic_url = _build_mssql_url(database_config)
    if dynamic_url:
        return dynamic_url
    return settings.mssql_url or settings.database_url


def get_engine(database_type: str = "postgresql", database_config=None) -> Engine:
    normalized = normalize_database_type(database_type)
    engine_key = _engine_key(normalized, database_config)
    if engine_key not in _engines:
        database_url = get_database_url(normalized, database_config)
        if not database_url:
            env_name = "POSTGRES_URL" if normalized == "postgresql" else "MSSQL_URL or DATABASE_URL"
            raise RuntimeError(f"{env_name} is missing in .env.")
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=_connect_args(normalized),
            future=True,
        )
        _attach_timeout(engine, get_settings().query_timeout_seconds)
        _engines[engine_key] = engine
    return _engines[engine_key]


@contextmanager
def get_connection(database_type: str = "postgresql", database_config=None) -> Iterator[Connection]:
    try:
        connection = get_engine(database_type, database_config).connect()
    except OperationalError:
        engine_key = _engine_key(normalize_database_type(database_type), database_config)
        engine = _engines.pop(engine_key, None)
        if engine is not None:
            engine.dispose()
        raise
    try:
        yield connection
    finally:
        connection.close()


def normalize_database_type(database_type: str | None) -> str:
    value = str(database_type or "postgresql").strip().lower()
    if value in {"postgres", "postgresql", "pg"}:
        return "postgresql"
    return "mssql"


def _with_postgres_ssl(database_url: str) -> str:
    if not database_url or "sslmode=" in database_url:
        return database_url
    separator = "&" if "?" in database_url else "?"
    return f"{database_url}{separator}sslmode=require"


def _build_mssql_url(database_config) -> str:
    if not database_config or normalize_database_type(getattr(database_config, "type", "")) != "mssql":
        return ""
    host = getattr(database_config, "host", "").strip()
    database = getattr(database_config, "database", "").strip()
    username = getattr(database_config, "username", "").strip()
    password = getattr(database_config, "password", "")
    if not all([host, database, username, password]):
        return ""
    port = getattr(database_config, "port", None)
    server = f"{host},{port}" if port else host
    driver = quote_plus(getattr(database_config, "driver", "ODBC Driver 17 for SQL Server"))
    user = quote_plus(username)
    secret = quote_plus(password)
    db_name = quote_plus(database)
    trust = "yes" if getattr(database_config, "trust_server_certificate", True) else "no"
    return f"mssql+pyodbc://{user}:{secret}@{server}/{db_name}?driver={driver}&TrustServerCertificate={trust}"


def _engine_key(database_type: str, database_config) -> str:
    dynamic_url = _build_mssql_url(database_config)
    if not dynamic_url:
        return database_type
    return f"{database_type}:{sha256(dynamic_url.encode()).hexdigest()}"


def _connect_args(database_type: str) -> dict[str, int]:
    timeout = get_settings().query_timeout_seconds
    if database_type == "postgresql":
        return {"connect_timeout": timeout}
    return {"timeout": timeout}



def _attach_timeout(engine: Engine, timeout_seconds: int) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def set_timeout(conn, cursor, statement, parameters, context, executemany):
        if hasattr(cursor, "timeout"):
            cursor.timeout = timeout_seconds
