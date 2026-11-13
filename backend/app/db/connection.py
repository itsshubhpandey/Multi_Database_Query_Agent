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
    dynamic_url = _build_database_url(normalized, database_config)
    if dynamic_url:
        return dynamic_url
    if normalized == "postgresql":
        return _with_postgres_ssl(settings.postgres_url)
    if normalized == "mysql":
        return settings.mysql_url
    if normalized == "mssql":
        return settings.mssql_url or settings.database_url
    raise RuntimeError("MongoDB connections are managed by the MongoDB connector.")


def get_engine(database_type: str = "postgresql", database_config=None) -> Engine:
    normalized = normalize_database_type(database_type)
    engine_key = _engine_key(normalized, database_config)
    if engine_key not in _engines:
        database_url = get_database_url(normalized, database_config)
        if not database_url:
            env_name = {
                "postgresql": "POSTGRES_URL",
                "mysql": "MYSQL_URL",
                "mssql": "MSSQL_URL or DATABASE_URL",
            }.get(normalized, f"{normalized.upper()}_URL")
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
    if value in {"mssql", "sqlserver", "sql_server", "sql server"}:
        return "mssql"
    if value in {"mysql", "mariadb"}:
        return "mysql"
    if value in {"mongo", "mongodb"}:
        return "mongodb"
    raise ValueError(f"Unsupported database type: {database_type}")


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


def _build_database_url(database_type: str, database_config) -> str:
    if not database_config:
        return ""
    connection_uri = str(getattr(database_config, "connection_uri", "") or "").strip()
    if connection_uri:
        if database_type == "postgresql" and connection_uri.startswith("postgres://"):
            return connection_uri.replace("postgres://", "postgresql+psycopg2://", 1)
        if database_type == "postgresql" and connection_uri.startswith("postgresql://"):
            return connection_uri.replace("postgresql://", "postgresql+psycopg2://", 1)
        if database_type == "mysql" and connection_uri.startswith("mysql://"):
            return connection_uri.replace("mysql://", "mysql+pymysql://", 1)
        return connection_uri
    if database_type == "mssql":
        return _build_mssql_url(database_config)
    if database_type not in {"postgresql", "mysql"}:
        return ""

    host = str(getattr(database_config, "host", "") or "").strip()
    database = str(getattr(database_config, "database", "") or "").strip()
    if not host or not database:
        return ""
    username = str(getattr(database_config, "username", "") or "").strip()
    password = str(getattr(database_config, "password", "") or "")
    default_port = 5432 if database_type == "postgresql" else 3306
    port = getattr(database_config, "port", None) or default_port
    scheme = "postgresql+psycopg2" if database_type == "postgresql" else "mysql+pymysql"
    auth = ""
    if username:
        auth = quote_plus(username)
        if password:
            auth += f":{quote_plus(password)}"
        auth += "@"
    return f"{scheme}://{auth}{host}:{port}/{quote_plus(database)}"


def _engine_key(database_type: str, database_config) -> str:
    dynamic_url = _build_database_url(database_type, database_config)
    if not dynamic_url:
        return database_type
    return f"{database_type}:{sha256(dynamic_url.encode()).hexdigest()}"


def _connect_args(database_type: str) -> dict[str, int]:
    timeout = get_settings().query_timeout_seconds
    if database_type == "postgresql":
        return {"connect_timeout": timeout}
    if database_type == "mysql":
        return {"connect_timeout": timeout}
    return {"timeout": timeout}



def _attach_timeout(engine: Engine, timeout_seconds: int) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def set_timeout(conn, cursor, statement, parameters, context, executemany):
        if hasattr(cursor, "timeout"):
            cursor.timeout = timeout_seconds
