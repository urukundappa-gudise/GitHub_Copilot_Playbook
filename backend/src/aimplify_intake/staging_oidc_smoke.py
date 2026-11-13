"""Verify deployed Entra discovery, login configuration, session resolution, and logout."""

from __future__ import annotations

import json
import os
import re
import sys
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx


def run_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    tenant_id: str,
    client_id: str,
    session_cookie: str,
) -> dict[str, str]:
    base = urlsplit(base_url)
    if base.scheme != "https" or not base.netloc or base.username or base.password:
        raise ValueError("STAGING_BASE_URL must be an HTTPS origin without credentials.")
    if not all((tenant_id, client_id, session_cookie)):
        raise ValueError("Tenant, client, and test-session settings are required.")
    if re.fullmatch(r"[A-Za-z0-9_-]+", session_cookie) is None:
        raise ValueError("OIDC_TEST_SESSION_COOKIE must be one opaque cookie value.")

    origin = f"{base.scheme}://{base.netloc}"
    discovery_url = (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0/"
        ".well-known/openid-configuration"
    )
    discovery_response = client.get(discovery_url)
    discovery_response.raise_for_status()
    discovery = discovery_response.json()
    expected_issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    if discovery.get("issuer", "").casefold() != expected_issuer.casefold():
        raise RuntimeError("Entra discovery issuer did not match the configured tenant.")
    for key in ("authorization_endpoint", "jwks_uri", "token_endpoint"):
        value = discovery.get(key)
        if not isinstance(value, str) or urlsplit(value).scheme != "https":
            raise RuntimeError("Entra discovery metadata is incomplete or insecure.")

    jwks_response = client.get(discovery["jwks_uri"])
    jwks_response.raise_for_status()
    if not isinstance(jwks_response.json().get("keys"), list) or not jwks_response.json()[
        "keys"
    ]:
        raise RuntimeError("Entra signing-key metadata is unavailable.")

    login_response = client.get(
        urljoin(f"{origin}/", "api/v1/auth/login"),
        follow_redirects=False,
    )
    if login_response.status_code != 302:
        raise RuntimeError("Staging login did not return an authorization redirect.")
    authorization = urlsplit(login_response.headers.get("location", ""))
    authorization_query = parse_qs(authorization.query)
    path_parts = authorization.path.strip("/").split("/")
    if (
        authorization.scheme != "https"
        or authorization.hostname != "login.microsoftonline.com"
        or not path_parts
        or path_parts[0].casefold() != tenant_id.casefold()
        or authorization_query.get("client_id") != [client_id]
        or authorization_query.get("code_challenge_method") != ["S256"]
        or not authorization_query.get("state")
        or not authorization_query.get("nonce")
    ):
        raise RuntimeError("Staging authorization redirect did not match Entra settings.")

    cookie_header = {"cookie": f"oidc_session={session_cookie}"}
    session_response = client.get(
        urljoin(f"{origin}/", "api/v1/auth/session"),
        headers=cookie_header,
    )
    if session_response.status_code != 200:
        raise RuntimeError("Staging session could not resolve the authenticated identity.")
    user = session_response.json().get("user")
    if not isinstance(user, dict) or not all(
        isinstance(user.get(field), str) and user[field]
        for field in ("oid", "upn", "name")
    ):
        raise RuntimeError("Staging session returned an incomplete identity context.")

    logout_response = client.post(
        urljoin(f"{origin}/", "api/v1/auth/logout"),
        headers={"origin": origin, **cookie_header},
        follow_redirects=False,
    )
    logout_url = urlsplit(logout_response.headers.get("location", ""))
    if (
        logout_response.status_code != 303
        or logout_url.scheme != "https"
        or logout_url.hostname != "login.microsoftonline.com"
        or "logout" not in logout_url.path
    ):
        raise RuntimeError("Staging logout did not initiate Entra session termination.")
    if (
        client.get(
            urljoin(f"{origin}/", "api/v1/auth/session"),
            headers=cookie_header,
        ).status_code
        != 401
    ):
        raise RuntimeError("Staging logout did not revoke the local session.")

    return {
        "entra_discovery": "passed",
        "entra_signing_keys": "passed",
        "login_redirect": "passed",
        "session_identity_resolution": "passed",
        "logout_and_revocation": "passed",
    }


def main() -> int:
    required = (
        "STAGING_BASE_URL",
        "AZURE_AD_TENANT_ID",
        "AZURE_AD_CLIENT_ID",
        "OIDC_TEST_SESSION_COOKIE",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("Missing required staging smoke-test environment settings: " + ", ".join(missing))
        return 2

    try:
        with httpx.Client(timeout=15) as client:
            checks = run_smoke(
                client,
                base_url=os.environ["STAGING_BASE_URL"],
                tenant_id=os.environ["AZURE_AD_TENANT_ID"],
                client_id=os.environ["AZURE_AD_CLIENT_ID"],
                session_cookie=os.environ["OIDC_TEST_SESSION_COOKIE"],
            )
    except (httpx.HTTPError, ValueError, RuntimeError):
        print("Staging OIDC smoke test failed; sensitive response details were suppressed.")
        return 1

    print(json.dumps({"result": "passed", "checks": checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
