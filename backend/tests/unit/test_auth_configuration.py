import runpy

import pytest
from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import (
    AuthConfigurationError,
    create_identity_verifier,
    load_auth_settings,
)


def test_production_requires_complete_oidc_configuration() -> None:
    with pytest.raises(AuthConfigurationError):
        load_auth_settings({"APP_ENV": "production", "AUTH_REQUIRED": "true"})


def test_complete_production_configuration_is_accepted() -> None:
    settings = load_auth_settings(
        {
            "APP_ENV": "production",
            "AUTH_REQUIRED": "true",
            "AZURE_AD_TENANT_ID": "tenant-id",
            "AZURE_AD_CLIENT_ID": "client-id",
            "AZURE_AD_CLIENT_SECRET": "client-secret",
            "AZURE_AD_REDIRECT_URI": "https://app.example.test/api/v1/auth/callback",
            "AZURE_AD_POST_LOGOUT_REDIRECT_URI": "https://app.example.test/",
        }
    )
    assert settings.auth_required is True
    assert settings.tenant_id == "tenant-id"
    assert settings.app_env == "production"


@pytest.mark.parametrize("app_env", ["development", "demo", "production"])
def test_mock_mode_is_rejected_outside_local_or_test(app_env: str) -> None:
    with pytest.raises(AuthConfigurationError):
        load_auth_settings({"APP_ENV": app_env, "AUTH_MOCK_MODE": "true"})


def test_mock_mode_requires_an_unset_tenant_and_explicit_opt_in() -> None:
    settings = load_auth_settings(
        {"APP_ENV": "test", "AUTH_REQUIRED": "true", "AUTH_MOCK_MODE": "true"}
    )
    assert settings.mock_mode is True
    with pytest.raises(AuthConfigurationError):
        load_auth_settings(
            {
                "APP_ENV": "test",
                "AUTH_MOCK_MODE": "true",
                "AZURE_AD_TENANT_ID": "configured-tenant",
            }
        )


def test_production_auth_cannot_be_disabled() -> None:
    with pytest.raises(AuthConfigurationError):
        load_auth_settings({"APP_ENV": "production", "AUTH_REQUIRED": "false"})


def test_required_auth_without_verifier_fails_closed_instead_of_using_demo_subject() -> None:
    settings = load_auth_settings({"APP_ENV": "test", "AUTH_REQUIRED": "true"})
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=settings,
    )
    with TestClient(app, headers={"origin": "http://testserver"}) as client:
        response = client.post("/api/v1/sessions")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_explicit_local_mock_login_uses_persisted_session() -> None:
    settings = load_auth_settings(
        {"APP_ENV": "test", "AUTH_REQUIRED": "true", "AUTH_MOCK_MODE": "true"}
    )
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=settings,
    )
    app.state.identity_verifier = create_identity_verifier(app.state.session_factory)
    with TestClient(app) as client:
        login = client.get("/api/v1/auth/login", follow_redirects=False)
        assert login.status_code == 303
        token = login.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        client.cookies.set("oidc_session", token)
        session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["oid"] == "local-test-employee"


def test_asgi_entrypoint_constructs_persistent_verifier(monkeypatch) -> None:
    for key, value in {
        "APP_ENV": "test",
        "AUTH_REQUIRED": "true",
        "AUTH_MOCK_MODE": "false",
        "AZURE_AD_TENANT_ID": "test-tenant",
        "AZURE_AD_CLIENT_ID": "test-client",
        "AZURE_AD_CLIENT_SECRET": "test-secret",
        "AZURE_AD_REDIRECT_URI": "https://app.example.test/api/v1/auth/callback",
        "AZURE_AD_POST_LOGOUT_REDIRECT_URI": "https://app.example.test/",
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
    }.items():
        monkeypatch.setenv(key, value)
    namespace = runpy.run_module("aimplify_intake.main", run_name="oidc_entrypoint_test")
    verifier = namespace["app"].state.identity_verifier
    assert callable(verifier)
    with pytest.raises(ValueError, match="Unauthenticated"):
        verifier("unknown-session")
