from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings, create_identity_verifier


class DeterministicProvider:
    async def authorization_url(
        self, *, state: str, nonce: str, pkce_verifier: str
    ) -> str:
        return (
            "https://provider.test/authorize"
            f"?state={state}&nonce={nonce}&code_challenge={pkce_verifier}"
            "&code_challenge_method=S256"
        )

    async def validate_authorization_code(
        self, *, code: str, nonce: str, pkce_verifier: str
    ) -> dict[str, str | None]:
        if code != "deterministic-code" or not nonce or not pkce_verifier:
            raise ValueError("Invalid deterministic authorization response.")
        return {
            "oid": "timing-test-employee",
            "upn": "timing@example.test",
            "email": None,
            "name": "Timing Test",
        }

    async def logout_url(self) -> str:
        return "https://provider.test/logout"


def test_100_deterministic_callbacks_issue_verified_sessions_within_two_minutes(
    record_property,
) -> None:
    settings = AuthSettings(
        tenant_id=None,
        client_id="deterministic-client",
        client_secret="deterministic-secret",
        redirect_uri="https://app.example.test/api/v1/auth/callback",
        post_logout_redirect_uri="https://app.example.test/",
        auth_required=True,
        app_env="test",
        mock_mode=False,
    )
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        auth_settings=settings,
        oidc_provider=DeterministicProvider(),
    )
    app.state.identity_verifier = create_identity_verifier(app.state.session_factory)
    durations: list[float] = []
    successful = 0

    with TestClient(app) as client:
        for index in range(100):
            login = client.get("/api/v1/auth/login", follow_redirects=False)
            assert login.status_code == 302
            query = parse_qs(urlsplit(login.headers["location"]).query)
            started = time.perf_counter()
            callback = client.get(
                "/api/v1/auth/callback",
                params={
                    "code": "deterministic-code",
                    "state": query["state"][0],
                },
                follow_redirects=False,
            )
            if callback.status_code != 303 or "oidc_session=" not in callback.headers.get(
                "set-cookie", ""
            ):
                continue
            token = callback.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
            client.cookies.set("oidc_session", token)
            verified = client.get("/api/v1/auth/session")
            durations.append(time.perf_counter() - started)
            if verified.status_code == 200:
                successful += 1
            assert verified.status_code == 200, f"callback {index} did not verify its session"

    under_threshold = sum(duration <= 120 for duration in durations)
    record_property("callback_count", len(durations))
    record_property("verified_sessions", successful)
    record_property("callback_p95_seconds", sorted(durations)[94])
    assert len(durations) == 100
    assert successful == 100
    assert under_threshold >= 95
