import json
from pathlib import Path

import pytest

from aimplify_intake.evaluation.golden_runner import (
    evaluate_case,
    load_cases,
    load_manifest,
    validate_case_coverage,
    validate_manifest,
)


def test_manifest_has_required_coverage_and_at_least_50_cases() -> None:
    golden_dir = Path(__file__).resolve().parents[2] / "golden"
    manifest_path = golden_dir / "golden_manifest.json"
    cases_path = golden_dir / "cases.jsonl"

    manifest = load_manifest(manifest_path)
    validate_manifest(manifest)
    cases = load_cases(cases_path)
    assert len(cases) >= 50


def test_golden_case_executes_intake_and_checks_its_expected_outcome() -> None:
    evaluate_case(
        {
            "id": "case-behavior",
            "modality": "chat",
            "claim": "The workflow saves 15 hours.",
        },
        {
            "accepted_fields": [
                "submitter_name",
                "idea_title",
                "target_beneficiaries",
                "submission_type",
                "reference_links",
            ],
            "rejected_fields": ["problem_statement"],
            "human_only_fields": [
                "declaration_accepted",
                "submitter_signature",
                "date_of_submission",
                "reviewer_notes",
            ],
            "human_only_omitted": True,
            "clarification_count": 1,
            "intake_status": "in_progress",
            "safety_notice": {
                "code": "NO_FACTS_REJECTED",
                "status": "denied",
                "reason": "NoFacts",
                "reasons": ["number"],
            },
        }
    )


def test_golden_case_fails_when_safety_notice_differs_from_expected() -> None:
    expected = {
        "accepted_fields": [
            "submitter_name",
            "idea_title",
            "target_beneficiaries",
            "submission_type",
            "reference_links",
        ],
        "rejected_fields": ["problem_statement"],
        "human_only_fields": [
            "declaration_accepted",
            "submitter_signature",
            "date_of_submission",
            "reviewer_notes",
        ],
        "human_only_omitted": True,
        "clarification_count": 1,
        "safety_notice": None,
    }

    with pytest.raises(AssertionError, match="safety notice"):
        evaluate_case(
            {
                "id": "case-notice-mismatch",
                "modality": "chat",
                "claim": "The workflow saves 15 hours.",
            },
            expected,
        )


def test_runner_rejects_cases_without_behavioral_expectations() -> None:
    golden_dir = Path(__file__).resolve().parents[2] / "golden"
    manifest_path = golden_dir / "golden_manifest.json"
    cases_path = golden_dir / "cases.jsonl"
    cases = load_cases(cases_path)
    cases[0].pop("claim")
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="claim and expected outcome"):
        validate_case_coverage(cases, manifest)


def test_runner_requires_single_question_and_human_only_manifest_flags(tmp_path: Path) -> None:
    source_manifest = load_manifest(Path(__file__).resolve().parents[2] / "golden" / "golden_manifest.json")
    source_manifest["required_coverage"]["single_question_pacing"] = False
    source_manifest["required_coverage"]["human_only_protection"] = False
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(json.dumps(source_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="single-question pacing"):
        validate_manifest(load_manifest(bad_manifest))


def test_golden_email_case_detects_a_canonical_validation_regression(monkeypatch) -> None:
    monkeypatch.setattr("aimplify_intake.schema.validation._validate_email", lambda _value: None)
    with pytest.raises(AssertionError, match="accepted unexpected"):
        evaluate_case(
            {"id": "invalid-email-policy", "modality": "chat",
             "claim": "Saves 15 hours.", "email": "user@example.c"},
            {"accepted_fields": ["submitter_name", "idea_title", "target_beneficiaries",
                                 "submission_type", "reference_links"],
             "rejected_fields": ["problem_statement", "submitter_email"],
             "human_only_omitted": True, "clarification_count": 1,
             "safety_notice": {"code": "NO_FACTS_REJECTED", "status": "denied",
                               "reason": "NoFacts", "reasons": ["number"]}},
        )
