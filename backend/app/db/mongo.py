from __future__ import annotations

from hashlib import sha256
from typing import Any
from urllib.parse import quote_plus

from backend.app.config import get_settings

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - exercised only when optional driver is absent
    MongoClient = None


_clients: dict[str, Any] = {}


def get_mongo_database(database_config=None):
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed. Run pip install -r backend/requirements.txt.")

    uri, database_name = get_mongo_connection_details(database_config)
    if not uri:
        raise RuntimeError("MONGODB_URL or submitted MongoDB connection settings are required.")

    key = sha256(uri.encode()).hexdigest()
    if key not in _clients:
        timeout_ms = get_settings().query_timeout_seconds * 1000
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms)
            client.admin.command("ping")
            _clients[key] = client
        except Exception as exc:
            raise RuntimeError(f"MongoDB connection failed: {exc}") from exc
    client = _clients[key]

    if database_name:
        return client[database_name]
    try:
        return client.get_default_database()
    except Exception as exc:
        raise RuntimeError("A MongoDB database name is required in the connection form or URI.") from exc


def get_mongo_connection_details(database_config=None) -> tuple[str, str]:
    settings = get_settings()
    if database_config:
        connection_uri = str(getattr(database_config, "connection_uri", "") or "").strip()
        database_name = str(getattr(database_config, "database", "") or "").strip()
        if connection_uri:
            return connection_uri, database_name

        host = str(getattr(database_config, "host", "") or "").strip()
        if host:
            port = getattr(database_config, "port", None) or 27017
            username = str(getattr(database_config, "username", "") or "").strip()
            password = str(getattr(database_config, "password", "") or "")
            auth_source = str(getattr(database_config, "auth_source", "admin") or "admin").strip()
            auth = ""
            if username:
                auth = quote_plus(username)
                if password:
                    auth += f":{quote_plus(password)}"
                auth += "@"
            database_path = f"/{quote_plus(database_name)}" if database_name else ""
            return f"mongodb://{auth}{host}:{port}{database_path}?authSource={quote_plus(auth_source)}", database_name
    return settings.mongodb_url, ""
