from aimplify_intake.graph.intake_graph import create_intake_graph
from aimplify_intake.schema.registry import load_canonical_schema
from aimplify_intake.services.extraction import DetailedExtractionResult

FIELDS = [
    {"key": "first", "mandatory": True, "clarification_prompt": "What is the first detail?"},
    {"key": "optional", "mandatory": False, "clarification_prompt": "Optional detail?"},
    {"key": "second", "mandatory": True, "clarification_prompt": "What is the second detail?"},
]


def test_graph_asks_one_question_then_advances_after_answer() -> None:
    graph = create_intake_graph(lambda _text: [])

    first_turn = graph.invoke(
        {"text": "Start", "canonical_fields": FIELDS, "current_values": {}}
    )
    resumed_turn = graph.invoke(
        {
            "text": "The first answer",
            "canonical_fields": FIELDS,
            "current_values": {"first": "Answered"},
        }
    )

    assert first_turn["clarification"] == {
        "field_key": "first",
        "question": "What is the first detail?",
    }
    assert resumed_turn["clarification"] == {
        "field_key": "second",
        "question": "What is the second detail?",
    }
    assert isinstance(first_turn["clarification"], dict)
    assert isinstance(resumed_turn["clarification"], dict)


def test_graph_asks_no_question_when_mandatory_fields_are_complete() -> None:
    graph = create_intake_graph(lambda _text: [])
    fields = load_canonical_schema()["fields"]
    current_values = {
        field["key"]: "Answered" for field in fields if field["mandatory"]
    }

    result = graph.invoke(
        {
            "text": "Complete",
            "canonical_fields": fields,
            "current_values": current_values,
        }
    )

    assert result["clarification"] is None
    assert result["field_updates"] == []


def test_graph_retry_is_deterministic_for_same_saved_state() -> None:
    graph = create_intake_graph(lambda _text: [])
    state = {"text": "Retry", "canonical_fields": FIELDS, "current_values": {}}

    first_attempt = graph.invoke(state)
    retry = graph.invoke(state)

    assert retry["clarification"] == first_attempt["clarification"]
    assert isinstance(retry["clarification"], dict)


def test_graph_propagates_safety_notice_without_changing_question_pacing() -> None:
    notice = {
        "code": "NO_FACTS_REJECTED",
        "status": "denied",
        "reason": "NoFacts",
        "reasons": ["number"],
    }
    graph = create_intake_graph(
        lambda _text: DetailedExtractionResult(
            field_updates=[
                {"field_key": "first", "value": "A safe response", "origin": "ai_extracted"}
            ],
            safety_notice=notice,
        )
    )

    result = graph.invoke(
        {"text": "Mixed answer", "canonical_fields": FIELDS, "current_values": {}}
    )

    assert result["field_updates"] == [
        {"field_key": "first", "value": "A safe response", "origin": "ai_extracted"}
    ]
    assert result["safety_notice"] == notice
    assert result["clarification"] == {
        "field_key": "second",
        "question": "What is the second detail?",
    }