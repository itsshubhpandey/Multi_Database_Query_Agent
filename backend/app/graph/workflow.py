from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.app.agents.nodes import (
    database_qa_node,
    english_to_sql_node,
    error_handler_node,
    sql_execution_node,
    sql_review_node,
    user_query_classifier_node,
)
from backend.app.models.state import AgentState


def route_after_classifier(state: AgentState) -> str:
    intent = state.get("intent", "database_qa")
    if intent in {"english_to_sql"}:
        return "english_to_sql"
    if intent in {"sql_execution", "sql_debugging"}:
        return "sql_review"
    return "database_qa"


def route_after_execution(state: AgentState) -> str:
    if state.get("success") is False and int(state.get("retry_count", 0)) < 1:
        return "error_handler"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("USER_QUERY_CLASSIFIER_NODE", user_query_classifier_node)
    graph.add_node("ENGLISH_TO_SQL_NODE", english_to_sql_node)
    graph.add_node("SQL_REVIEW_NODE", sql_review_node)
    graph.add_node("SQL_EXECUTION_NODE", sql_execution_node)
    graph.add_node("DATABASE_QA_NODE", database_qa_node)
    graph.add_node("ERROR_HANDLER_NODE", error_handler_node)

    graph.add_edge(START, "USER_QUERY_CLASSIFIER_NODE")
    graph.add_conditional_edges(
        "USER_QUERY_CLASSIFIER_NODE",
        route_after_classifier,
        {
            "english_to_sql": "ENGLISH_TO_SQL_NODE",
            "sql_review": "SQL_REVIEW_NODE",
            "database_qa": "DATABASE_QA_NODE",
        },
    )
    graph.add_edge("ENGLISH_TO_SQL_NODE", "SQL_REVIEW_NODE")
    graph.add_edge("SQL_REVIEW_NODE", "SQL_EXECUTION_NODE")
    graph.add_conditional_edges(
        "SQL_EXECUTION_NODE",
        route_after_execution,
        {"error_handler": "ERROR_HANDLER_NODE", END: END},
    )
    graph.add_edge("ERROR_HANDLER_NODE", "SQL_REVIEW_NODE")
    graph.add_edge("DATABASE_QA_NODE", END)
    return graph.compile()


sql_agent_graph = build_graph()
