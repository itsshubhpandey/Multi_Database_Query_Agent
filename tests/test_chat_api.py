from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.models.schemas import OrchestrationResponse, ToolTrace
from backend.main import app


class StubOrchestrationAgent:
    def handle(self, request):
        assert request.message == "Show customer count"
        assert request.current_sql == "SELECT 1"
        return OrchestrationResponse(
            intent="data_question",
            message="Approve the generated query.",
            sql="SELECT COUNT(*) FROM customers",
            approval_required=True,
            tools=[ToolTrace(name="generate_sql", endpoint="/api/query/generate")],
        )


def test_chat_endpoint_returns_structured_orchestration_response(monkeypatch) -> None:
    monkeypatch.setattr(routes, "orchestration_agent", StubOrchestrationAgent())
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Show customer count",
            "current_sql": "SELECT 1",
            "database": {"type": "postgresql"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "data_question"
    assert payload["approval_required"] is True
    assert payload["tools"][0]["endpoint"] == "/api/query/generate"


def test_cors_allows_frontend_on_any_local_development_port() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://127.0.0.1:3004",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3004"
