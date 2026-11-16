from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

import aimplify_intake.api.app as app_module
from aimplify_intake.api.app import create_app
from aimplify_intake.persistence.repositories import create_submission, persist_ai_values
from aimplify_intake.persistence.models import FieldValue, IdeaSubmission
from sqlalchemy import select
from aimplify_intake.services.extraction import extract_safe_candidates

_ATTACKS = {
    "numeral": "The workflow saves 15 hours.",
    "percentage": "The workflow improves efficiency by ninety percent.",
    "cost": "The workflow costs $200.",
    "date": "The workflow launches on 2026-01-02.",
    "word_quantity": "The workflow saves over fifteen hours.",
}
_DOCUMENT_TYPES = {
    "pdf": ("application/pdf", "application/pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
}
_AUDIO_TYPES = {
    "wav": ("audio/wav", "audio/wav"),
    "mp3": ("audio/mpeg", "audio/mpeg"),
    "webm": ("audio/webm", "audio/webm"),
}
_REASONS = {
    "numeral": ["number"],
    "percentage": ["percentage", "word_quantity"],
    "cost": ["number", "cost"],
    "date": ["number", "date"],
    "word_quantity": ["word_quantity"],
}


@pytest.mark.parametrize("claim", _ATTACKS.values(), ids=_ATTACKS.keys())
@pytest.mark.parametrize("transport", ["http", "websocket"])
@pytest.mark.parametrize(
    "modality,source_type",
    [("chat", None)]
    + [("document", source_type) for source_type in _DOCUMENT_TYPES]
    + [("audio", source_type) for source_type in _AUDIO_TYPES],
)
def test_unverified_claims_never_reach_persistence_or_client_events(
    monkeypatch: pytest.MonkeyPatch,
    claim: str,
    transport: str,
    modality: str,
    source_type: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def read_source(source: BytesIO, *_args: object, **_kwargs: object) -> str:
        return source.read().decode("utf-8")

    for parser_name in ("extract_pdf", "extract_docx", "extract_pptx", "transcribe_audio"):
        monkeypatch.setattr(app_module, parser_name, read_source)

    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=lambda _cookie: {"subject": "employee-1"},
        candidate_extractor=lambda text: {"problem_statement": text, "idea_title": "Workflow helper"},
        transcription_no_retention_approved=True,
    )
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "test-session")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        with app.state.session_factory() as session:
            submission = session.get(IdeaSubmission, session_id)
            assert submission is not None
            persist_ai_values(session, submission, extract_safe_candidates(
                "", lambda _text: {"problem_statement": "Existing safe detail"}
            ))
            session.commit()

        if modality == "chat" and transport == "http":
            response = client.post(
                f"/api/v1/sessions/{session_id}/messages",
                json={"request_id": "unsafe-chat", "text": claim},
            )
            assert response.status_code == 200
            assert [update["field_key"] for update in response.json()["field_updates"]] == ["idea_title"]
            notice = response.json()["safety_notice"]
            client_output = response.text
        elif modality == "chat":
            with client.websocket_connect(
                f"/api/v1/sessions/{session_id}/stream",
                headers={"origin": "http://testserver"},
                subprotocols=["aimplify.intake.v1"],
            ) as websocket:
                websocket.send_json(
                    {
                        "type": "client.message",
                        "request_id": "unsafe-chat",
                        "payload": {"text": claim},
                    }
                )
                events = [websocket.receive_json(), websocket.receive_json(), websocket.receive_json()]
            assert events[-1]["type"] == "server.submission.status"
            notice = events[-1]["payload"]["safety_notice"]
            client_output = str(events)
        else:
            source_type = source_type or ""
            content_type, media_type = (_DOCUMENT_TYPES | _AUDIO_TYPES)[source_type]
            payload = claim.encode("utf-8")
            if transport == "http":
                response = client.post(
                    f"/api/v1/sessions/{session_id}/sources/{source_type}",
                    content=payload,
                    headers={"content-type": content_type},
                )
                assert response.status_code == 200
                assert [update["field_key"] for update in response.json()["field_updates"]] == ["idea_title"]
                notice = response.json()["safety_notice"]
                client_output = response.text
            else:
                with client.websocket_connect(
                    f"/api/v1/sessions/{session_id}/stream",
                    headers={"origin": "http://testserver"},
                    subprotocols=["aimplify.intake.v1"],
                ) as websocket:
                    websocket.send_json(
                        {
                            "type": "client.source.begin",
                            "request_id": "unsafe-begin",
                            "payload": {
                                "source_id": "source-1",
                                "media_type": media_type,
                                "filename": "source.bin",
                                "size_bytes": len(payload),
                            },
                        }
                    )
                    assert websocket.receive_json()["type"] == "server.source.ready"
                    websocket.send_bytes(payload)
                    websocket.send_json(
                        {
                            "type": "client.source.commit",
                            "request_id": "unsafe-commit",
                            "payload": {"source_id": "source-1"},
                        }
                    )
                    events = []
                    while True:
                        event = websocket.receive_json()
                        events.append(event)
                        if event["type"] == "server.source.completed":
                            break
                assert events[-2]["type"] == "server.submission.status"
                notice = events[-2]["payload"]["safety_notice"]
                client_output = str(events)

        field_state = client.get(f"/api/v1/sessions/{session_id}/fields").json()
        problem_statement = next(
            field
            for section in field_state["sections"]
            for field in section["fields"]
            if field["field_key"] == "problem_statement"
        )
        assert problem_statement["value"] == "Existing safe detail"
        category = next(key for key, value in _ATTACKS.items() if value == claim)
        assert notice == {
            "code": "NO_FACTS_REJECTED", "status": "denied", "reason": "NoFacts",
            "reasons": _REASONS[category],
        }
        assert "Workflow helper" in client_output
        assert claim not in client_output
        assert claim not in caplog.text
        with app.state.session_factory() as session:
            assert claim not in list(session.scalars(select(FieldValue.value)))


def test_persistence_rejects_ai_updates_without_no_facts_validation() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")
    with app.state.session_factory() as session:
        submission = create_submission(session, "employee-1")

        with pytest.raises(ValueError, match="NoFacts"):
            persist_ai_values(
                session,
                submission,
                [
                    {
                        "field_key": "problem_statement",
                        "value": "The workflow saves 15 hours.",
                        "origin": "ai_extracted",
                    }
                ],
            )


def test_persistence_rejects_candidate_mutated_after_no_facts_validation() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")
    updates = extract_safe_candidates(
        "Transient source text.",
        lambda _text: {"problem_statement": "Policy discovery can be simplified."},
    )
    updates[0]["value"] = "The workflow saves 15 hours."

    with app.state.session_factory() as session:
        submission = create_submission(session, "employee-1")
        with pytest.raises(ValueError, match="NoFacts"):
            persist_ai_values(session, submission, updates)