import json
from pathlib import Path

import pytest

from aimplify_intake.evaluation.golden_runner import (
    evaluate_auth_access,
    evaluate_case,
    load_cases,
    load_manifest,
    run_golden_evaluation,
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
        }
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


def test_golden_cases_evaluate_authenticated_and_unauthenticated_access() -> None:
    golden_dir = Path(__file__).resolve().parents[2] / "golden"
    manifest = load_manifest(golden_dir / "golden_manifest.json")
    cases = load_cases(golden_dir / "cases.jsonl")
    validate_manifest(manifest)
    validate_case_coverage(cases, manifest)
    access_cases = [case for case in cases if case.get("auth_access")]
    assert {case["auth_access"] for case in access_cases} == {
        "authenticated",
        "unauthenticated",
    }
    for case in access_cases:
        evaluate_auth_access(case)


def test_standalone_runner_routes_auth_cases_to_access_checks(monkeypatch) -> None:
    golden_dir = Path(__file__).resolve().parents[2] / "golden"
    cases = load_cases(golden_dir / "cases.jsonl")
    intake_cases: list[str] = []
    auth_cases: list[str] = []
    monkeypatch.setattr(
        "aimplify_intake.evaluation.golden_runner.evaluate_case",
        lambda case, _expected: intake_cases.append(case["id"]),
    )
    monkeypatch.setattr(
        "aimplify_intake.evaluation.golden_runner.evaluate_auth_access",
        lambda case: auth_cases.append(case["id"]),
    )

    _, evaluated = run_golden_evaluation(
        golden_dir / "golden_manifest.json",
        golden_dir / "cases.jsonl",
    )
    assert len(evaluated) == len(cases)
    assert len(intake_cases) == sum(case.get("auth_access") is None for case in cases)
    assert len(auth_cases) == sum(case.get("auth_access") is not None for case in cases)
