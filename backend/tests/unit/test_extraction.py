from aimplify_intake.services.extraction import (
    extract_detailed_candidates,
    extract_safe_candidates,
)


def test_extraction_drops_unsafe_invalid_and_human_only_candidates() -> None:
    candidates = extract_safe_candidates(
        "Transient source text.",
        lambda _text: {
            "problem_statement": "Policy discovery is difficult.",
            "expected_benefits": "Reduce effort by 20 percent.",
            "aimplify_platform": "Unknown platform",
            "declaration_accepted": True,
            "reviewer_notes": "Keep this for a reviewer.",
        },
    )

    assert candidates == [
        {
            "field_key": "problem_statement",
            "value": "Policy discovery is difficult.",
            "origin": "ai_extracted",
        }
    ]


def test_detailed_extraction_returns_only_safe_updates_and_category_notice() -> None:
    result = extract_detailed_candidates(
        "Transient source text.",
        lambda _text: {
            "problem_statement": "Policy discovery is difficult.",
            "expected_benefits": "Reduce effort by 20 percent.",
            "unknown_field": "Saves 30 hours.",
            "idea_title": "",
        },
    )

    assert result.field_updates == [
        {
            "field_key": "problem_statement",
            "value": "Policy discovery is difficult.",
            "origin": "ai_extracted",
        }
    ]
    assert result.safety_notice == {
        "code": "NO_FACTS_REJECTED",
        "status": "denied",
        "reason": "NoFacts",
        "reasons": ["number", "percentage"],
    }
    assert "20 percent" not in str(result)
    assert "30 hours" not in str(result)


def test_detailed_extraction_does_not_classify_unknown_or_invalid_candidates() -> None:
    result = extract_detailed_candidates(
        "Transient source text.",
        lambda _text: {
            "unknown_field": "Saves 30 hours.",
            "idea_title": "",
        },
    )

    assert result.field_updates == []
    assert result.safety_notice is None