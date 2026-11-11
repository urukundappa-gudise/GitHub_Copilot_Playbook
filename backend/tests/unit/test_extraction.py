from aimplify_intake.services.extraction import (
    extract_detailed_candidates,
    extract_safe_candidates,
)
from aimplify_intake.safety.no_facts import is_no_facts_validated
import pytest


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


@pytest.mark.parametrize("candidate", ["A safe description.", "Saves fifteen hours."])
def test_detailed_results_preserve_legacy_interface_and_proofs(candidate: str) -> None:
    extractor = lambda _text: {"problem_statement": candidate}
    detailed = extract_detailed_candidates("", extractor)
    assert detailed.field_updates == extract_safe_candidates("", extractor)
    if detailed.field_updates:
        assert detailed.safety_notice is None
        assert all(is_no_facts_validated(update) for update in detailed.field_updates)
    else:
        assert detailed.safety_notice is not None
        assert candidate not in str(detailed)