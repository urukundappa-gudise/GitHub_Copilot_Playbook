from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings, create_identity_verifier
from aimplify_intake.persistence.repositories import create_oidc_session


def _app():
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
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=settings,
    )
    app.state.identity_verifier = create_identity_verifier(app.state.session_factory)
    return app


def test_session_verifier_resolves_claims_from_token_digest() -> None:
    app = _app()
    token = "opaque-session-value"
    with app.state.session_factory() as session:
        create_oidc_session(
            session,
            token,
            {
                "oid": "verified-oid",
                "upn": "verified@infovision.example",
                "email": None,
                "name": "Verified Employee",
            },
        )
    with TestClient(app) as client:
        client.cookies.set("oidc_session", token)
        response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["user"] == {
        "oid": "verified-oid",
        "upn": "verified@infovision.example",
        "email": None,
        "name": "Verified Employee",
    }


def test_invalid_expired_and_revoked_tokens_are_rejected() -> None:
    app = _app()
    token = "expires-session"
    revoked_token = "revoked-session"
    now = datetime.now(UTC)
    with app.state.session_factory() as session:
        create_oidc_session(
            session,
            token,
            {"oid": "oid", "upn": "upn", "email": None, "name": "name"},
            expires_at=now - timedelta(seconds=1),
        )
        create_oidc_session(
            session,
            revoked_token,
            {"oid": "oid", "upn": "upn", "email": None, "name": "name"},
        )
    with app.state.session_factory() as session:
        from aimplify_intake.persistence.repositories import revoke_oidc_session

        assert revoke_oidc_session(session, revoked_token)
    with TestClient(app) as client:
        for token_value in ("unknown-token", token, revoked_token):
            client.cookies.set("oidc_session", token_value)
            response = client.get("/api/v1/auth/session")
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "UNAUTHENTICATED"
            assert response.headers["cache-control"] == "no-store"


def test_runtime_entrypoint_builds_verifier_and_create_app_keeps_injection() -> None:
    injected = lambda _token: {"subject": "test-subject"}
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        identity_verifier=injected,
    )
    assert app.state.identity_verifier is injected


def test_create_app_builds_runtime_verifier_from_its_session_factory() -> None:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=AuthSettings(
            tenant_id=None,
            client_id=None,
            client_secret=None,
            redirect_uri=None,
            post_logout_redirect_uri=None,
            auth_required=True,
            app_env="test",
            mock_mode=False,
        ),
        identity_verifier_factory=create_identity_verifier,
    )
    assert callable(app.state.identity_verifier)
    with pytest.raises(ValueError, match="Unauthenticated"):
        app.state.identity_verifier("unknown-session")
