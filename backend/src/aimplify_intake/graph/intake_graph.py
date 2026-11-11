"""LangGraph coordinator for one safe intake turn and its clarification."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aimplify_intake.graph.pacing import select_next_clarification
from aimplify_intake.services.extraction import DetailedExtractionResult


class IntakeState(TypedDict, total=False):
    text: str
    canonical_fields: list[dict[str, Any]]
    current_values: dict[str, Any]
    field_updates: list[dict[str, str]]
    clarification: dict[str, str] | None
    safety_notice: dict[str, object] | None


def create_intake_graph(
    extract_safe_values: Callable[[str], list[dict[str, str]] | DetailedExtractionResult],
) -> Any:
    def extract(state: IntakeState) -> dict[str, Any]:
        result = extract_safe_values(state["text"])
        if isinstance(result, DetailedExtractionResult):
            return {
                "field_updates": result.field_updates,
                "safety_notice": result.safety_notice,
            }
        return {"field_updates": result, "safety_notice": None}

    def validate(state: IntakeState) -> dict[str, Any]:
        values = dict(state["current_values"])
        values.update(
            {update["field_key"]: update["value"] for update in state["field_updates"]}
        )
        return {"current_values": values}

    def choose_question(state: IntakeState) -> dict[str, Any]:
        decision = select_next_clarification(
            state["canonical_fields"], state["current_values"]
        )
        return {
            "clarification": (
                {"field_key": decision.field_key, "question": decision.question}
                if decision
                else None
            )
        }

    def route_question(state: IntakeState) -> str:
        return "ask" if state["clarification"] is not None else "complete"

    builder = StateGraph(IntakeState)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("choose_question", choose_question)
    builder.add_node("ask", lambda state: {"clarification": state["clarification"]})
    builder.add_node("complete", lambda _state: {"clarification": None})
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "validate")
    builder.add_edge("validate", "choose_question")
    builder.add_conditional_edges(
        "choose_question", route_question, {"ask": "ask", "complete": "complete"}
    )
    builder.add_edge("ask", END)
    builder.add_edge("complete", END)
    return builder.compile()