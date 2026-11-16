from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import aimplify_intake.api.app as app_module
from aimplify_intake.api.app import create_app
from aimplify_intake.persistence.models import FieldValue, IdeaSubmission
from aimplify_intake.persistence.repositories import SubmissionUnavailableError
from aimplify_intake.schema.registry import load_canonical_schema


def _client() -> TestClient:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "employee-1"},
    )
    client = TestClient(app, headers={"origin": "http://testserver"})
    client.cookies.set("oidc_session", "test-session")
    return client


def _fill_required_fields(client: TestClient, session_id: str) -> None:
    fields = load_canonical_schema()["fields"]
    with client.app.state.session_factory() as session:
        for definition in fields:
            if not definition["mandatory"]:
                continue
            value_type = definition["value_type"]
            if value_type == "boolean":
                value = "true"
            elif value_type == "date":
                value = date.today().isoformat()
            elif value_type == "email":
                value = "employee@example.com"
            elif value_type == "enum":
                value = definition["allowed_values"][0]
            else:
                value = "A qualitative test response."
            session.add(
                FieldValue(
                    submission_id=session_id,
                    field_key=definition["key"],
                    value=value,
                    origin="human_entered" if not definition["ai_writable"] else "ai_extracted",
                )
            )
        session.commit()


def test_incomplete_submission_returns_only_safe_field_keys() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        response = client.post(f"/api/v1/sessions/{session_id}/submit", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "SUBMISSION_INCOMPLETE"
    assert error["message"] == "Complete the required information and save your declaration before submitting."
    assert error["missing_fields"]
    assert error["invalid_fields"] == []
    assert all(isinstance(key, str) and "@" not in key for key in error["missing_fields"])


def test_successful_submission_retry_returns_the_same_committed_receipt() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        _fill_required_fields(client, session_id)
        first = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
        second = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
        fields = client.get(f"/api/v1/sessions/{session_id}/fields").json()
        with client.app.state.session_factory() as session:
            submissions = session.scalars(
                select(IdeaSubmission).where(IdeaSubmission.subject_ref == "employee-1")
            ).all()

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["session_id"] == session_id
    assert first.json()["status"] == "submitted"
    assert first.json()["submitted_at"]
    assert fields["submitted_at"] == first.json()["submitted_at"]
    assert fields["readiness"]["ready"] is True
    assert len(submissions) == 1


def test_submitted_session_rejects_human_and_message_mutations() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        _fill_required_fields(client, session_id)
        submitted = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
        field_response = client.put(
            f"/api/v1/sessions/{session_id}/fields/submitter_signature",
            json={"value": "Changed after submit"},
        )
        message_response = client.post(
            f"/api/v1/sessions/{session_id}/messages",
            json={"request_id": "late-message", "text": "A late update."},
        )

    assert submitted.status_code == 200
    for response in (field_response, message_response):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SUBMISSION_CLOSED"


def test_stored_invalid_email_blocks_submission_without_deleting_value() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        _fill_required_fields(client, session_id)
        with client.app.state.session_factory() as session:
            email = session.scalar(
                select(FieldValue).where(
                    FieldValue.submission_id == session_id,
                    FieldValue.field_key == "submitter_email",
                )
            )
            assert email is not None
            email.value = "employee@xn--e28h.de"
            session.commit()
        response = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
        fields = client.get(f"/api/v1/sessions/{session_id}/fields").json()

    assert response.status_code == 422
    assert response.json()["error"]["invalid_fields"] == ["submitter_email"]
    assert fields["readiness"]["invalid_fields"] == ["submitter_email"]
    assert fields["readiness"]["ready"] is False
    assert fields["sections"][0]["fields"]
    assert "employee@xn--e28h.de" in str(fields["sections"])


def test_false_declaration_blocks_submission() -> None:
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        _fill_required_fields(client, session_id)
        with client.app.state.session_factory() as session:
            declaration = session.scalar(
                select(FieldValue).where(
                    FieldValue.submission_id == session_id,
                    FieldValue.field_key == "declaration_accepted",
                )
            )
            assert declaration is not None
            declaration.value = "false"
            session.commit()
        response = client.post(f"/api/v1/sessions/{session_id}/submit", json={})

    assert response.status_code == 422
    assert response.json()["error"]["invalid_fields"] == ["declaration_accepted"]


def test_submitted_session_rejects_http_source_and_open_websocket_source_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aimplify_intake.api.app.extract_pdf", lambda _source: "Safe source text.")
    payload = b"in-memory PDF source"
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        _fill_required_fields(client, session_id)
        with client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": "http://testserver"},
            subprotocols=["aimplify.intake.v1"],
        ) as websocket:
            websocket.send_json({
                "type": "client.source.begin",
                "request_id": "source-begin-before-submit",
                "payload": {
                    "source_id": "source-before-submit",
                    "media_type": "application/pdf",
                    "size_bytes": len(payload),
                },
            })
            assert websocket.receive_json()["type"] == "server.source.ready"
            websocket.send_bytes(payload)
            submission = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
            websocket.send_json({
                "type": "client.source.commit",
                "request_id": "source-commit-after-submit",
                "payload": {"source_id": "source-before-submit"},
            })
            closed_event = websocket.receive_json()
            websocket.send_json({
                "type": "client.message",
                "request_id": "message-after-submit",
                "payload": {"text": "A late safe message."},
            })
            closed_message = websocket.receive_json()
        http_source = client.post(
            f"/api/v1/sessions/{session_id}/sources/pdf",
            content=payload,
            headers={"content-type": "application/pdf"},
        )

    assert submission.status_code == 200
    assert closed_event["type"] == "server.error"
    assert closed_event["request_id"] == "source-commit-after-submit"
    assert closed_event["payload"]["code"] == "SUBMISSION_CLOSED"
    assert closed_message["type"] == "server.error"
    assert closed_message["request_id"] == "message-after-submit"
    assert closed_message["payload"]["code"] == "SUBMISSION_CLOSED"
    assert http_source.status_code == 409
    assert http_source.json()["error"]["code"] == "SUBMISSION_CLOSED"


def test_submission_persistence_unavailable_returns_safe_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: object) -> None:
        raise SubmissionUnavailableError()

    monkeypatch.setattr(app_module, "finalize_submission", unavailable)
    with _client() as client:
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        response = client.post(f"/api/v1/sessions/{session_id}/submit", json={})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["error"]["message"] == "The intake service is temporarily unavailable."


def test_submission_requires_owner_and_allowed_origin() -> None:
    identity = {"subject": "employee-1"}
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: identity,
    )
    client = TestClient(app, headers={"origin": "http://testserver"})
    client.cookies.set("oidc_session", "test-session")
    session_id = client.post("/api/v1/sessions").json()["session_id"]

    identity["subject"] = "employee-2"
    unowned = client.post(f"/api/v1/sessions/{session_id}/submit", json={})
    identity["subject"] = "employee-1"
    forbidden_origin = client.post(
        f"/api/v1/sessions/{session_id}/submit",
        json={},
        headers={"origin": "https://attacker.invalid"},
    )

    assert unowned.status_code == 404
    assert unowned.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert forbidden_origin.status_code == 403
    assert forbidden_origin.json()["error"]["code"] == "FORBIDDEN"