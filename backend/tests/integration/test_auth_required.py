from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings, create_identity_verifier
from aimplify_intake.persistence.repositories import create_oidc_session, revoke_oidc_session


def _settings() -> AuthSettings:
    return AuthSettings(
        tenant_id=None,
        client_id=None,
        client_secret=None,
        redirect_uri=None,
        post_logout_redirect_uri=None,
        auth_required=True,
        app_env="test",
        mock_mode=False,
    )


def _app(*, real_session: bool = False):
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        allowed_origins={"http://testserver"},
        auth_settings=_settings(),
        candidate_extractor=lambda _text: {},
    )
    if real_session:
        app.state.identity_verifier = create_identity_verifier(app.state.session_factory)
    else:
        def verify(token: str):
            if token != "valid-cookie":
                raise ValueError("Invalid session.")
            return {"subject": "verified-employee-oid"}

        app.state.identity_verifier = verify
    return app


def test_required_auth_denies_every_intake_http_and_websocket_path() -> None:
    app = _app()
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "valid-cookie")
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        client.cookies.clear()

        responses = [
            client.post("/api/v1/sessions"),
            client.get(f"/api/v1/sessions/{session_id}/fields"),
            client.put(
                f"/api/v1/sessions/{session_id}/fields/idea_title",
                json={"value": "A verified idea"},
            ),
            client.post(
                f"/api/v1/sessions/{session_id}/messages",
                json={"request_id": "unauthenticated", "text": "An idea"},
            ),
            client.post(
                f"/api/v1/sessions/{session_id}/sources/pdf",
                content=b"not-a-document",
                headers={"content-type": "application/pdf"},
            ),
        ]
        assert [response.status_code for response in responses] == [401] * 5
        assert all(
            response.json()["error"]["code"] == "UNAUTHENTICATED"
            for response in responses
        )
        with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": "http://testserver"},
            subprotocols=["aimplify.intake.v1"],
        ):
            pass
        assert error.value.code == 4401


def test_verified_session_can_use_http_and_websocket_intake_paths() -> None:
    app = _app()
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", "valid-cookie")
        created = client.post("/api/v1/sessions")
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        assert client.get(f"/api/v1/sessions/{session_id}/fields").status_code == 200
        assert (
            client.put(
                f"/api/v1/sessions/{session_id}/fields/declaration_accepted",
                json={"value": True},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/sessions/{session_id}/messages",
                json={"request_id": "authenticated", "text": "An idea"},
            ).status_code
            == 200
        )
        source = client.post(
            f"/api/v1/sessions/{session_id}/sources/pdf",
            content=b"not-a-document",
            headers={"content-type": "application/pdf"},
        )
        assert source.status_code != 401
        with client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": "http://testserver"},
            subprotocols=["aimplify.intake.v1"],
        ) as websocket:
            websocket.send_json(
                {
                    "type": "client.message",
                    "request_id": "authenticated-socket",
                    "payload": {"text": "An idea"},
                }
            )
            assert websocket.receive_json()["request_id"] == "authenticated-socket"


def test_revoked_session_cannot_read_or_modify_its_prior_submission() -> None:
    app = _app(real_session=True)
    token = "revocable-session-cookie"
    with app.state.session_factory() as session:
        create_oidc_session(
            session,
            token,
            {
                "oid": "verified-employee-oid",
                "upn": "employee@infovision.example",
                "email": None,
                "name": "Verified Employee",
            },
        )
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        client.cookies.set("oidc_session", token)
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        with app.state.session_factory() as session:
            assert revoke_oidc_session(session, token)
        read = client.get(f"/api/v1/sessions/{session_id}/fields")
        write = client.put(
            f"/api/v1/sessions/{session_id}/fields/idea_title",
            json={"value": "Must not persist"},
        )
    assert read.status_code == 401
    assert write.status_code == 401
