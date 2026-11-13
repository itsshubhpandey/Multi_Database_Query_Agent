from backend.app.db.connection import get_database_url, normalize_database_type
from backend.app.models.schemas import DatabaseSelection
from backend.app.services.mongo_execution_service import MongoExecutionService


def test_database_type_aliases_are_normalized() -> None:
    assert normalize_database_type("postgres") == "postgresql"
    assert normalize_database_type("sql server") == "mssql"
    assert normalize_database_type("mariadb") == "mysql"
    assert normalize_database_type("mongo") == "mongodb"


def test_dynamic_postgres_connection_uses_submitted_credentials() -> None:
    selection = DatabaseSelection(
        type="postgresql",
        host="db.example.com",
        port=5433,
        database="analytics",
        username="data user",
        password="secret value",
    )

    url = get_database_url("postgresql", selection)

    assert url == "postgresql+psycopg2://data+user:secret+value@db.example.com:5433/analytics"


def test_mysql_uri_is_upgraded_to_pymysql_driver() -> None:
    selection = DatabaseSelection(
        type="mysql",
        connection_uri="mysql://reporter:secret@localhost:3306/reports",
    )

    assert get_database_url("mysql", selection) == "mysql+pymysql://reporter:secret@localhost:3306/reports"


def test_mongodb_rejects_write_operations_before_connecting() -> None:
    result = MongoExecutionService().execute(
        '{"operation":"update_many","collection":"users","filter":{}}',
        DatabaseSelection(type="mongodb"),
    )

    assert result.success is False
    assert "Only read operations are allowed" in result.error
