from __future__ import annotations

from urllib.parse import urlencode

import httpx
import pytest

from aimplify_intake.staging_oidc_smoke import run_smoke


def _client(*, client_id: str = "test-client") -> httpx.Client:
    tenant_id = "test-tenant"
    origin = "https://staging.example.test"
    discovery_url = (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0/"
        ".well-known/openid-configuration"
    )
    authorization_url = (
        "https://login.microsoftonline.com/"
        f"{tenant_id}/oauth2/v2.0/authorize?"
        + urlencode(
            {
                "client_id": client_id,
                "state": "synthetic-state",
                "nonce": "synthetic-nonce",
                "code_challenge_method": "S256",
            }
        )
    )
    logged_out = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal logged_out
        if request.url == httpx.URL(discovery_url):
            return httpx.Response(
                200,
                json={
                    "issuer": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
                    "authorization_endpoint": (
                        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
                    ),
                    "token_endpoint": (
                        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                    ),
                    "jwks_uri": f"{discovery_url}/keys",
                },
            )
        if request.url == httpx.URL(f"{discovery_url}/keys"):
            return httpx.Response(200, json={"keys": [{"kid": "synthetic-key"}]})
        if request.url == httpx.URL(f"{origin}/api/v1/auth/login"):
            return httpx.Response(302, headers={"location": authorization_url})
        if request.url == httpx.URL(f"{origin}/api/v1/auth/session"):
            if logged_out:
                return httpx.Response(401)
            return httpx.Response(
                200,
                json={
                    "user": {
                        "oid": "synthetic-oid",
                        "upn": "synthetic@infovision.example",
                        "name": "Synthetic Employee",
                    }
                },
            )
        if request.url == httpx.URL(f"{origin}/api/v1/auth/logout"):
            logged_out = True
            return httpx.Response(
                303,
                headers={
                    "location": (
                        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
                    )
                },
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_staging_smoke_checks_discovery_session_resolution_and_logout() -> None:
    with _client() as client:
        checks = run_smoke(
            client,
            base_url="https://staging.example.test",
            tenant_id="test-tenant",
            client_id="test-client",
            session_cookie="synthetic-session-cookie",
        )

    assert checks == {
        "entra_discovery": "passed",
        "entra_signing_keys": "passed",
        "login_redirect": "passed",
        "session_identity_resolution": "passed",
        "logout_and_revocation": "passed",
    }


def test_staging_smoke_requires_https_origin() -> None:
    with _client() as client, pytest.raises(ValueError, match="HTTPS"):
        run_smoke(
            client,
            base_url="http://staging.example.test",
            tenant_id="test-tenant",
            client_id="test-client",
            session_cookie="synthetic-session-cookie",
        )
