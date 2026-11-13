from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi.testclient import TestClient

from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import AuthSettings, create_identity_verifier


class SyntheticPersonaProvider:
    def __init__(self, persona: int) -> None:
        self.client_id = f"synthetic-client-{persona}"
        self.identity = {
            "oid": f"synthetic-oid-{persona}",
            "upn": f"employee-{persona}@infovision.example",
            "email": f"employee-{persona}@infovision.example",
            "name": f"Synthetic Employee {persona}",
        }
        self.transaction: dict[str, str] | None = None

    async def authorization_url(
        self, *, state: str, nonce: str, pkce_verifier: str
    ) -> str:
        self.transaction = {
            "state": state,
            "nonce": nonce,
            "pkce_verifier": pkce_verifier,
        }
        return "https://login.example.test/authorize?" + urlencode(
            {
                "state": state,
                "nonce": nonce,
                "code_challenge": "synthetic-challenge",
                "code_challenge_method": "S256",
            }
        )

    async def validate_authorization_code(
        self, *, code: str, nonce: str, pkce_verifier: str
    ) -> dict[str, str | None]:
        assert self.transaction is not None
        assert code == "synthetic-code"
        assert nonce == self.transaction["nonce"]
        assert pkce_verifier == self.transaction["pkce_verifier"]
        return self.identity

    async def logout_url(self) -> str:
        return f"https://login.example.test/logout?client_id={self.client_id}"


def test_ten_synthetic_personas_resolve_context_and_complete_logout(record_property) -> None:
    successes = 0
    persona_count = 10

    for persona in range(persona_count):
        provider = SyntheticPersonaProvider(persona)
        settings = AuthSettings(
            tenant_id=None,
            client_id=provider.client_id,
            client_secret="synthetic-secret",
            redirect_uri="https://app.example.test/api/v1/auth/callback",
            post_logout_redirect_uri="https://app.example.test/",
            auth_required=True,
            app_env="test",
            mock_mode=False,
        )
        app = create_app(
            database_url="sqlite+pysqlite:///:memory:",
            allowed_origins={"http://testserver"},
            auth_settings=settings,
            oidc_provider=provider,
        )
        app.state.identity_verifier = create_identity_verifier(app.state.session_factory)

        with TestClient(app) as client:
            login = client.get("/api/v1/auth/login", follow_redirects=False)
            assert login.status_code == 302
            login_query = parse_qs(urlsplit(login.headers["location"]).query)
            state = login_query["state"][0]

            callback = client.get(
                "/api/v1/auth/callback",
                params={"code": "synthetic-code", "state": state},
                follow_redirects=False,
            )
            assert callback.status_code == 303
            cookie = callback.headers["set-cookie"].split(";", 1)[0]
            session_token = cookie.split("=", 1)[1]
            client.cookies.set("oidc_session", session_token)

            context = client.get("/api/v1/auth/session")
            assert context.status_code == 200
            assert context.json()["user"] == provider.identity

            logout = client.post(
                "/api/v1/auth/logout",
                headers={"origin": "http://testserver"},
                follow_redirects=False,
            )
            assert logout.status_code == 303
            assert "/logout" in logout.headers["location"]
            assert client.get("/api/v1/auth/session").status_code == 401
            successes += 1

    record_property("synthetic_personas", persona_count)
    record_property("synthetic_persona_successes", successes)
    record_property("human_usability_evidence", False)
    print(
        "Synthetic persona regression only "
        f"(not employee usability evidence): {successes}/{persona_count} passed."
    )
    assert successes >= 9, (
        "Synthetic persona regression threshold not met: "
        f"{successes}/{persona_count} passed."
    )
