"""Sibling App Runner origins are allowed only for the cohort demo policy."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings


def _client(monkeypatch: pytest.MonkeyPatch, *, app_origin: str | None = None) -> TestClient:
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://configured.example,https://second.example")
    if app_origin is not None:
        monkeypatch.setenv("APP_ORIGIN", app_origin)
    else:
        monkeypatch.delenv("APP_ORIGIN", raising=False)
    return TestClient(create_app(allowed_origins=None))


@pytest.mark.parametrize(
    "origin,app_origin",
    [
        ("https://configured.example", None),
        ("https://app.example", "https://app.example"),
        ("https://sibling.awsapprunner.com", None),
        ("http://testserver", None),
    ],
)
def test_http_accepts_configured_apprunner_and_same_host_origins(
    monkeypatch: pytest.MonkeyPatch, origin: str, app_origin: str | None
) -> None:
    with _client(monkeypatch, app_origin=app_origin) as client:
        response = client.post("/api/v1/sessions", headers={"origin": origin})

    assert response.status_code == 201


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "not-an-origin",
        "https://",
        "https://attacker.invalid",
        "https://sibling.awsapprunner.com.attacker.invalid",
        "https://sibling.awsapprunner.com/path",
        "https://user@sibling.awsapprunner.com",
        "https://.awsapprunner.com",
        "https://-sibling.awsapprunner.com",
        "https://sibling..awsapprunner.com",
    ],
)
def test_http_rejects_missing_malformed_and_unapproved_origins(
    monkeypatch: pytest.MonkeyPatch, origin: str | None
) -> None:
    with _client(monkeypatch) as client:
        headers = {} if origin is None else {"origin": origin}
        response = client.post("/api/v1/sessions", headers=headers)

    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin,app_origin",
    [
        ("https://configured.example", None),
        ("https://app.example", "https://app.example"),
        ("https://sibling.awsapprunner.com", None),
        ("http://testserver", None),
    ],
)
def test_websocket_accepts_configured_apprunner_and_same_host_origins(
    monkeypatch: pytest.MonkeyPatch, origin: str, app_origin: str | None
) -> None:
    with _client(monkeypatch, app_origin=app_origin) as client:
        session_id = client.post(
            "/api/v1/sessions", headers={"origin": "http://testserver"}
        ).json()["session_id"]
        with client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers={"origin": origin},
            subprotocols=["aimplify.intake.v1"],
        ):
            pass


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "not-an-origin",
        "https://attacker.invalid",
        "https://sibling.awsapprunner.com.attacker.invalid",
    ],
)
def test_websocket_rejects_missing_malformed_and_unapproved_origins(
    monkeypatch: pytest.MonkeyPatch, origin: str | None
) -> None:
    with _client(monkeypatch) as client:
        session_id = client.post(
            "/api/v1/sessions", headers={"origin": "http://testserver"}
        ).json()["session_id"]
        headers = {} if origin is None else {"origin": origin}
        with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect(
            f"/api/v1/sessions/{session_id}/stream",
            headers=headers,
            subprotocols=["aimplify.intake.v1"],
        ):
            pass

    assert error.value.code == 4403


def test_required_auth_rejects_unapproved_sibling_apprunner_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://approved.example")
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    settings = AuthSettings(
        tenant_id=None,
        client_id=None,
        client_secret=None,
        redirect_uri=None,
        post_logout_redirect_uri=None,
        auth_required=True,
        app_env="production",
        mock_mode=False,
    )
    app = create_app(auth_settings=settings)
    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/sessions",
            headers={"origin": "https://unapproved.awsapprunner.com"},
        )
        approved = client.post(
            "/api/v1/sessions",
            headers={"origin": "https://approved.example"},
        )
        same_host = client.post(
            "/api/v1/sessions",
            headers={"origin": "http://testserver"},
        )
    assert rejected.status_code == 403
    assert approved.status_code == 401
    assert same_host.status_code == 403
