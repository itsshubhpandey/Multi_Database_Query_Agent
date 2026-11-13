from backend.app.models.schemas import (
    ChatRequest,
    DatabaseSelection,
    QueryExecutionResponse,
    SchemaColumn,
    SchemaResponse,
    SchemaTable,
)
from backend.app.orchestration.agent import OrchestrationAgent


class FakeAiService:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    def invoke(self, system_prompt: str, user_prompt: str) -> str:
        return self.responses.pop(0)


class FakeToolbox:
    endpoints = {
        "generate_sql": "/api/query/generate",
        "review_sql": "/api/query/review",
        "execute_sql": "/api/query/execute",
        "get_schema": "/api/schema",
        "answer_database_question": "/api/chat",
    }

    def __init__(self, execution_success: bool = True) -> None:
        self.calls: list[str] = []
        self.execution_success = execution_success

    def generate_sql(self, question, database):
        self.calls.append("generate_sql")
        return {"sql": "SELECT COUNT(*) AS customer_count FROM customers", "explanation": "Counts customers."}

    def review_sql(self, sql, database, error=None):
        self.calls.append("review_sql")
        corrected = "SELECT COUNT(*) AS customer_count FROM customers" if error else sql
        return {"sql": corrected, "issues": [], "optimization_tips": []}

    def execute_sql(self, sql, database):
        self.calls.append("execute_sql")
        if not self.execution_success:
            return QueryExecutionResponse(success=False, query=sql, error="missing table")
        return QueryExecutionResponse(
            success=True,
            query=sql,
            data=[{"customer_count": 42}],
            columns=["customer_count"],
            row_count=1,
            execution_time=0.01,
        )

    def get_schema(self, database):
        self.calls.append("get_schema")
        return SchemaResponse(
            tables=[
                SchemaTable(
                    schema_name="public",
                    table_name="customers",
                    columns=[SchemaColumn(name="id", type="integer", nullable=False)],
                )
            ]
        )

    def answer_database_question(self, question, database):
        self.calls.append("answer_database_question")
        return "An index speeds up reads at the cost of additional write work."


def chat_request(message: str, **values) -> ChatRequest:
    return ChatRequest(message=message, database=DatabaseSelection(), **values)


def test_data_question_generates_and_reviews_sql_before_requesting_approval() -> None:
    toolbox = FakeToolbox()
    agent = OrchestrationAgent(
        toolbox=toolbox,
        ai_service=FakeAiService('{"intent":"data_question","reason":"Needs database rows"}'),
    )

    response = agent.handle(chat_request("How many customers do we have?"))

    assert response.intent == "data_question"
    assert response.approval_required is True
    assert response.sql.startswith("SELECT COUNT")
    assert [tool.name for tool in response.tools] == ["generate_sql", "review_sql"]
    assert toolbox.calls == ["generate_sql", "review_sql"]


def test_approved_sql_executes_and_returns_an_answer_from_query_results() -> None:
    toolbox = FakeToolbox()
    agent = OrchestrationAgent(
        toolbox=toolbox,
        ai_service=FakeAiService("There are 42 customers."),
    )

    response = agent.handle(
        chat_request(
            "How many customers do we have?",
            approved_sql="SELECT COUNT(*) AS customer_count FROM customers",
        )
    )

    assert response.success is True
    assert response.message == "There are 42 customers."
    assert response.result is not None and response.result.data == [{"customer_count": 42}]
    assert [tool.name for tool in response.tools] == ["execute_sql"]
    assert toolbox.calls == ["execute_sql"]


def test_failed_execution_is_sent_to_review_and_requires_new_approval() -> None:
    toolbox = FakeToolbox(execution_success=False)
    agent = OrchestrationAgent(toolbox=toolbox, ai_service=FakeAiService())

    response = agent.handle(
        chat_request("Run this", approved_sql="SELECT * FROM missing_customers")
    )

    assert response.success is False
    assert response.approval_required is True
    assert [tool.name for tool in response.tools] == ["execute_sql", "review_sql"]
    assert response.tools[0].status == "failed"
    assert toolbox.calls == ["execute_sql", "review_sql"]


def test_schema_intent_uses_schema_tool_without_generating_sql() -> None:
    toolbox = FakeToolbox()
    agent = OrchestrationAgent(toolbox=toolbox, ai_service=FakeAiService())

    response = agent.handle(chat_request("Which tables are available?"))

    assert response.database_schema is not None
    assert "public.customers" in response.message
    assert toolbox.calls == ["get_schema"]
