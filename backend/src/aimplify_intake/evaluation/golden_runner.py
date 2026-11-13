"""Golden evaluation manifest and result checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

import aimplify_intake.api.app as app_module
from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings
from aimplify_intake.schema.registry import load_canonical_schema

REQUIRED_NOFACTS = {"number", "date", "cost", "percentage", "word_quantity"}
REQUIRED_MODALITIES = {"chat", "document", "audio"}
REQUIRED_SECTIONS = {
    "section_01",
    "section_02",
    "section_03",
    "section_04",
    "section_05",
    "section_06",
}
REQUIRED_HUMAN_ONLY_FIELDS = {
    "declaration_accepted",
    "submitter_signature",
    "date_of_submission",
}
HUMAN_ONLY_FIELDS = REQUIRED_HUMAN_ONLY_FIELDS | {"reviewer_notes"}
EVALUATED_FIELD_KEYS = {
    "submitter_name",
    "idea_title",
    "problem_statement",
    "target_beneficiaries",
    "submission_type",
    "reference_links",
    *HUMAN_ONLY_FIELDS,
}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        records.append(json.loads(text))
    return records


def validate_manifest(manifest: dict[str, Any]) -> None:
    minimum_cases = manifest.get("minimum_cases")
    if not isinstance(minimum_cases, int) or minimum_cases < 50:
        raise ValueError("Golden manifest minimum_cases must be >= 50.")

    required_coverage = manifest.get("required_coverage", {})
    sections = set(required_coverage.get("sections", []))
    no_facts_categories = set(required_coverage.get("no_facts_categories", []))
    modalities = set(required_coverage.get("modalities", []))
    human_only_fields = set(required_coverage.get("human_only_fields", []))

    if sections != REQUIRED_SECTIONS:
        raise ValueError("Manifest must require all six canonical sections.")
    if no_facts_categories != REQUIRED_NOFACTS:
        raise ValueError("Manifest must require all NoFacts categories.")
    if modalities != REQUIRED_MODALITIES:
        raise ValueError("Manifest must require all three modalities.")
    if human_only_fields != REQUIRED_HUMAN_ONLY_FIELDS:
        raise ValueError("Manifest must require all human-only declaration fields.")

    if not required_coverage.get("single_question_pacing", False):
        raise ValueError("Manifest must require single-question pacing coverage.")
    if not required_coverage.get("human_only_protection", False):
        raise ValueError("Manifest must require human-only protection coverage.")
    if set(required_coverage.get("auth_access_outcomes", [])) != {
        "authenticated",
        "unauthenticated",
    }:
        raise ValueError(
            "Manifest must require authenticated and unauthenticated access coverage."
        )


def validate_case_coverage(cases: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    minimum_cases = manifest["minimum_cases"]
    if len(cases) < minimum_cases:
        raise ValueError(f"Golden suite must include at least {minimum_cases} cases.")

    schema = load_canonical_schema()
    section_coverage = {
        field["section_key"]
        for field in schema["fields"]
        if field["key"] in EVALUATED_FIELD_KEYS
    }
    no_facts_coverage = {category for case in cases for category in case.get("no_facts_categories", [])}
    modality_coverage = {case.get("modality") for case in cases}
    expected_outcomes = manifest.get("expected_outcomes", {})
    profiles = {
        case.get("expected_outcome")
        for case in cases
        if case.get("expected_outcome") in expected_outcomes
    }
    human_only_coverage = {
        field
        for profile in profiles
        for field in expected_outcomes[profile].get("human_only_fields", [])
    }
    auth_access_coverage = {
        case.get("auth_access")
        for case in cases
        if case.get("auth_access") is not None
    }

    if not REQUIRED_SECTIONS.issubset(section_coverage):
        raise ValueError("Golden cases are missing canonical section coverage.")
    if not REQUIRED_NOFACTS.issubset(no_facts_coverage):
        raise ValueError("Golden cases are missing NoFacts category coverage.")
    if not REQUIRED_MODALITIES.issubset(modality_coverage):
        raise ValueError("Golden cases are missing modality coverage.")
    if not REQUIRED_HUMAN_ONLY_FIELDS.issubset(human_only_coverage):
        raise ValueError("Golden cases are missing human-only field coverage.")
    if not {"authenticated", "unauthenticated"}.issubset(auth_access_coverage):
        raise ValueError("Golden cases are missing authentication access coverage.")

    if not any(
        expected_outcomes[profile].get("clarification_count") == 1 for profile in profiles
    ):
        raise ValueError("Golden cases must include single-question pacing coverage.")
    if not any(
        expected_outcomes[profile].get("human_only_omitted") is True for profile in profiles
    ):
        raise ValueError("Golden cases must include human-only protection coverage.")

    case_ids = [case.get("id") for case in cases]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
        raise ValueError("Every golden case must have a non-empty ID.")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Golden case IDs must be unique.")
    for case in cases:
        if case.get("modality") not in REQUIRED_MODALITIES:
            raise ValueError(f"Golden case {case['id']} has an unsupported modality.")
        if not isinstance(case.get("claim"), str) or case.get("expected_outcome") not in expected_outcomes:
            raise ValueError(f"Golden case {case['id']} must define a claim and expected outcome.")
        if len(case.get("no_facts_categories", [])) != 1:
            raise ValueError(f"Golden case {case['id']} must target one NoFacts category.")
        if case.get("auth_access") not in {None, "authenticated", "unauthenticated"}:
            raise ValueError(f"Golden case {case['id']} has an unsupported auth access outcome.")


def evaluate_case(case: dict[str, Any], expected: dict[str, Any]) -> None:
    claim = case["claim"]
    candidates = {
        "submitter_name": "Alex Example",
        "idea_title": "Automate policy discovery",
        "problem_statement": claim,
        "target_beneficiaries": "Operations teams",
        "submission_type": "General Idea",
        "reference_links": "Internal workflow notes",
        "declaration_accepted": True,
        "submitter_signature": "Alex Example",
        "date_of_submission": "not submitted",
        "reviewer_notes": "Human notes only",
    }
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "golden-employee"},
        candidate_extractor=lambda _text: candidates,
        transcription_provider=lambda _stream, _media_type: claim,
        transcription_no_retention_approved=True,
    )

    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "golden-session")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        if case["modality"] == "chat":
            response = client.post(
                f"/api/v1/sessions/{session_id}/messages",
                json={"request_id": case["id"], "text": claim},
            )
        elif case["modality"] == "document":
            with patch.object(app_module, "extract_pdf", return_value=claim):
                response = client.post(
                    f"/api/v1/sessions/{session_id}/sources/pdf",
                    content=b"golden-document",
                    headers={"content-type": "application/pdf"},
                )
        else:
            with patch.object(app_module, "transcribe_audio", return_value=claim):
                response = client.post(
                    f"/api/v1/sessions/{session_id}/sources/wav",
                    content=b"golden-audio",
                    headers={"content-type": "audio/wav"},
                )

        if response.status_code != 200:
            raise AssertionError(f"Golden case {case['id']} returned HTTP {response.status_code}.")
        result = response.json()
        accepted_fields = {update["field_key"] for update in result["field_updates"]}
        rejected_fields = {"idea_title", "problem_statement"} - accepted_fields
        if accepted_fields != set(expected["accepted_fields"]):
            raise AssertionError(f"Golden case {case['id']} accepted unexpected fields.")
        if rejected_fields != set(expected["rejected_fields"]):
            raise AssertionError(f"Golden case {case['id']} rejected unexpected fields.")
        if any(update["field_key"] in HUMAN_ONLY_FIELDS for update in result["field_updates"]):
            raise AssertionError(f"Golden case {case['id']} exposed an AI value for a human-only field.")
        clarification_count = int(result["clarification"] is not None)
        if clarification_count != expected["clarification_count"]:
            raise AssertionError(f"Golden case {case['id']} returned an unexpected clarification count.")
        human_only_omitted = not accepted_fields.intersection(HUMAN_ONLY_FIELDS)
        if human_only_omitted != expected["human_only_omitted"]:
            raise AssertionError(f"Golden case {case['id']} violated human-only field protection.")
        if claim in json.dumps(result, ensure_ascii=True):
            raise AssertionError(f"Golden case {case['id']} exposed a rejected claim.")

        field_state = client.get(f"/api/v1/sessions/{session_id}/fields").json()
        stored_fields = {
            field["field_key"]
            for section in field_state["sections"]
            for field in section["fields"]
            if "value" in field
        }
        if stored_fields != accepted_fields:
            raise AssertionError(f"Golden case {case['id']} persisted unexpected fields.")
        if stored_fields.intersection(HUMAN_ONLY_FIELDS):
            raise AssertionError(f"Golden case {case['id']} persisted an AI human-only field.")


def evaluate_auth_access(case: dict[str, Any]) -> None:
    outcome = case.get("auth_access")
    if outcome is None:
        return
    settings = AuthSettings(
        tenant_id=None,
        client_id=None,
        client_secret=None,
        redirect_uri=None,
        post_logout_redirect_uri=None,
        auth_required=True,
        app_env="test",
        mock_mode=False,
    )

    def verify(cookie: str) -> dict[str, str]:
        if cookie != "golden-authenticated":
            raise ValueError("Unauthenticated.")
        return {"subject": "golden-employee"}

    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        allowed_origins={"http://testserver"},
        auth_settings=settings,
        identity_verifier=verify,
    )
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "golden-authenticated")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        if outcome == "unauthenticated":
            client.cookies.clear()
            response = client.get(f"/api/v1/sessions/{session_id}/fields")
            create_response = client.post("/api/v1/sessions")
            if response.status_code != 401 or create_response.status_code != 401:
                raise AssertionError(
                    f"Golden case {case['id']} did not deny unauthenticated access."
                )
        else:
            response = client.get(f"/api/v1/sessions/{session_id}/fields")
            if response.status_code != 200:
                raise AssertionError(
                    f"Golden case {case['id']} did not allow authenticated access."
                )


def run_golden_evaluation(
    manifest_path: Path, cases_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_manifest(manifest_path)
    cases = load_cases(cases_path)
    validate_manifest(manifest)
    validate_case_coverage(cases, manifest)
    for case in cases:
        if case.get("auth_access") is None:
            evaluate_case(case, manifest["expected_outcomes"][case["expected_outcome"]])
        else:
            evaluate_auth_access(case)
    return manifest, cases
