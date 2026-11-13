from __future__ import annotations

import json
import re
from typing import Any

from backend.app.models.schemas import ChatRequest, OrchestrationResponse, ToolTrace
from backend.app.orchestration.tools import AgentToolbox
from backend.app.prompts.sql_prompts import ORCHESTRATOR_PROMPT, QUERY_RESULT_SUMMARY_PROMPT
from backend.app.services.ai_service import AiService
from backend.app.utils.json_helpers import parse_json_object
from backend.app.utils.sql_safety import looks_like_sql


VALID_INTENTS = {
    "data_question",
    "generate_sql",
    "review_sql",
    "execute_sql",
    "schema_question",
    "database_qa",
}


class OrchestrationAgent:
    """Routes a chat turn through the workspace's registered database tools."""

    def __init__(self, toolbox: AgentToolbox | None = None, ai_service: AiService | None = None) -> None:
        self.toolbox = toolbox or AgentToolbox()
        self.ai_service = ai_service or AiService()

    def handle(self, request: ChatRequest) -> OrchestrationResponse:
        if request.approved_sql:
            return self._execute_approved(request)

        intent = self._classify(request)
        if intent == "schema_question":
            return self._handle_schema(request)
        if intent == "database_qa":
            return self._handle_database_qa(request)
        if intent in {"data_question", "generate_sql", "review_sql", "execute_sql"}:
            return self._prepare_sql(request, intent)

        return OrchestrationResponse(
            intent="database_qa",
            message="I could not determine the requested database action. Please rephrase the question.",
        )

    def _classify(self, request: ChatRequest) -> str:
        if looks_like_sql(request.message) or self._looks_like_mongo_command(request.message):
            return "review_sql"

        recent_history = request.history[-6:]
        context = {
            "message": request.message,
            "has_current_sql": bool(request.current_sql.strip()),
            "recent_history": recent_history,
        }
        try:
            response = self.ai_service.invoke(ORCHESTRATOR_PROMPT, json.dumps(context, ensure_ascii=False))
            parsed = parse_json_object(response, {})
            intent = str(parsed.get("intent", "")).strip().lower()
            if intent in VALID_INTENTS:
                return intent
        except Exception:
            pass
        return self._heuristic_intent(request.message, bool(request.current_sql.strip()))

    @staticmethod
    def _heuristic_intent(message: str, has_current_sql: bool) -> str:
        text = message.lower()
        if has_current_sql and re.search(r"\b(run|execute|approve|go ahead)\b", text):
            return "execute_sql"
        if has_current_sql and re.search(r"\b(review|fix|debug|optimi[sz]e|validate|explain this)\b", text):
            return "review_sql"
        if re.search(r"\b(schema|tables?|columns?|relationships?)\b", text):
            return "schema_question"
        if re.search(r"\b(write|generate|create)\b.*\b(sql|query)\b", text):
            return "generate_sql"
        if re.search(r"\b(show|find|list|count|total|average|top|bottom|trend|revenue|sales|orders?|customers?|users?)\b", text):
            return "data_question"
        return "database_qa"

    def _prepare_sql(self, request: ChatRequest, intent: str) -> OrchestrationResponse:
        tools: list[ToolTrace] = []

        if intent in {"review_sql", "execute_sql"}:
            sql = self._extract_sql(request.message, request.current_sql)
            if not sql:
                return OrchestrationResponse(
                    intent=intent,
                    message="Include a database query in your message, then ask me to review or run it.",
                )
        else:
            generated = self.toolbox.generate_sql(request.message, request.database)
            tools.append(self._trace("generate_sql"))
            sql = generated.get("sql", "").strip()
            if not sql:
                explanation = generated.get("explanation") or "I need more schema detail before I can write that query."
                return OrchestrationResponse(intent=intent, message=explanation, tools=tools)

        reviewed = self.toolbox.review_sql(sql, request.database)
        tools.append(self._trace("review_sql"))
        corrected_sql = reviewed.get("sql", sql).strip()
        issues = reviewed.get("issues", [])
        tips = reviewed.get("optimization_tips", [])

        details: list[str] = []
        if issues:
            details.append(f"I found {len(issues)} review issue{'s' if len(issues) != 1 else ''} and applied the suggested correction.")
        if tips:
            details.append(f"I also found {len(tips)} optimization suggestion{'s' if len(tips) != 1 else ''}.")
        if intent == "review_sql":
            lead = "I reviewed the query and prepared the verified version."
        elif intent == "execute_sql":
            lead = "The query is reviewed and ready. Approve it before I execute it."
        elif intent == "generate_sql":
            lead = "I generated and reviewed the query. You can ask for changes or approve it to run."
        else:
            lead = "I translated your question into a database query and reviewed it. Approve it so I can fetch the answer."

        return OrchestrationResponse(
            intent=intent,
            message=" ".join([lead, *details]),
            tools=tools,
            sql=corrected_sql,
            approval_required=True,
        )

    def _execute_approved(self, request: ChatRequest) -> OrchestrationResponse:
        sql = request.approved_sql.strip()
        result = self.toolbox.execute_sql(sql, request.database)
        trace = self._trace("execute_sql", "completed" if result.success else "failed")
        if not result.success:
            tools = [trace]
            corrected_sql = sql
            correction_note = ""
            try:
                reviewed = self.toolbox.review_sql(sql, request.database, error=result.error)
                corrected_sql = reviewed.get("sql", sql).strip()
                tools.append(self._trace("review_sql"))
                correction_note = " I reviewed the failure and placed a corrected query below. Check it before approving another run."
            except Exception:
                correction_note = " Review the database error and connection details before trying again."
            return OrchestrationResponse(
                success=False,
                intent="execute_sql",
                message=f"The database rejected the query: {result.error or 'Unknown database error.'}{correction_note}",
                tools=tools,
                sql=corrected_sql,
                approval_required=True,
                result=result,
            )

        message = self._summarize_result(request.message, sql, result.model_dump(mode="json"))
        return OrchestrationResponse(
            intent="execute_sql",
            message=message,
            tools=[trace],
            sql=sql,
            result=result,
        )

    def _handle_schema(self, request: ChatRequest) -> OrchestrationResponse:
        schema = self.toolbox.get_schema(request.database)
        table_names = [f"{table.schema_name}.{table.table_name}" for table in schema.tables]
        if table_names:
            preview = ", ".join(table_names[:8])
            suffix = " …" if len(table_names) > 8 else ""
            message = f"I found {len(table_names)} table{'s' if len(table_names) != 1 else ''}: {preview}{suffix}"
        else:
            message = "The connected database did not return any user tables."
        return OrchestrationResponse(
            intent="schema_question",
            message=message,
            tools=[self._trace("get_schema")],
            database_schema=schema,
        )

    def _handle_database_qa(self, request: ChatRequest) -> OrchestrationResponse:
        answer = self.toolbox.answer_database_question(request.message, request.database)
        return OrchestrationResponse(
            intent="database_qa",
            message=answer or "I could not produce an answer for that database question.",
            tools=[self._trace("answer_database_question")],
        )

    def _summarize_result(self, question: str, sql: str, result: dict[str, Any]) -> str:
        if not result.get("data"):
            return f"The query completed successfully and returned {result.get('row_count', 0)} row(s)."
        payload = {
            "question": question,
            "sql": sql,
            "columns": result.get("columns", []),
            "rows": result.get("data", [])[:50],
            "row_count": result.get("row_count", 0),
        }
        try:
            return self.ai_service.invoke(QUERY_RESULT_SUMMARY_PROMPT, json.dumps(payload, default=str, ensure_ascii=False))
        except Exception:
            return f"The query completed successfully and returned {result.get('row_count', 0)} row(s)."

    def _trace(self, name: str, status: str = "completed") -> ToolTrace:
        return ToolTrace(name=name, endpoint=self.toolbox.endpoints[name], status=status)

    @staticmethod
    def _extract_sql(message: str, current_sql: str) -> str:
        if current_sql.strip():
            return current_sql.strip()
        fenced = re.search(r"```(?:sql)?\s*([\s\S]*?)```", message, re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        return message.strip() if looks_like_sql(message) or OrchestrationAgent._looks_like_mongo_command(message) else ""

    @staticmethod
    def _looks_like_mongo_command(message: str) -> bool:
        text = message.strip()
        return text.startswith("{") and '"operation"' in text and '"collection"' in text
