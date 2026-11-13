from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import import_key

import aimplify_intake.api.auth as auth_module
from aimplify_intake.api.app import create_app
from aimplify_intake.api.auth import (
    AuthSettings,
    EntraOidcProvider,
    OidcProviderError,
    create_identity_verifier,
)
from aimplify_intake.persistence.models import OidcApplicationSession, OidcLoginTransaction


class ProviderFixture:
    def __init__(self) -> None:
        self.failure: str | None = None
        self.logout_failure = False
        self.identity: dict[str, str | None] = {
            "oid": "employee-object-id",
            "upn": "employee@infovision.example",
            "email": "employee@infovision.example",
            "name": "InfoVision Employee",
        }
        self.transaction: dict[str, str] | None = None

    async def authorization_url(
        self, *, state: str, nonce: str, pkce_verifier: str
    ) -> str:
        self.transaction = {"state": state, "nonce": nonce, "pkce_verifier": pkce_verifier}
        return (
            "https://login.example.test/authorize"
            f"?state={state}&nonce={nonce}&code_challenge=challenge"
            "&code_challenge_method=S256"
        )

    async def validate_authorization_code(
        self, *, code: str, nonce: str, pkce_verifier: str
    ) -> dict[str, str | None]:
        assert self.transaction is not None
        assert code == "synthetic-code"
        assert nonce == self.transaction["nonce"]
        assert pkce_verifier == self.transaction["pkce_verifier"]
        if self.failure:
            raise OidcProviderError(self.failure)
        return self.identity

    async def logout_url(self) -> str:
        if self.logout_failure:
            raise OidcProviderError("Provider logout is unavailable.")
        return "https://login.example.test/logout?client_id=synthetic-client"


def _client(provider: ProviderFixture) -> tuple[TestClient, ProviderFixture]:
    settings = AuthSettings(
        tenant_id=None,
        client_id="synthetic-client",
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
    return TestClient(app), provider


def _begin_login(client: TestClient) -> tuple[str, dict[str, str]]:
    response = client.get("/api/v1/auth/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"]
    assert query["nonce"]
    assert query["code_challenge"]
    return query["state"][0], query


def test_login_redirect_persists_transaction_and_uses_pkce() -> None:
    client, provider = _client(ProviderFixture())
    with client:
        state, query = _begin_login(client)
        assert provider.transaction is not None
        assert provider.transaction["state"] == state
        assert provider.transaction["nonce"] == query["nonce"][0]
        with client.app.state.session_factory() as session:
            assert session.query(OidcLoginTransaction).count() == 1
            transaction = session.query(OidcLoginTransaction).one()
            assert transaction.state_digest != state
            assert transaction.pkce_verifier


def test_callback_establishes_opaque_secure_cookie_and_optional_email() -> None:
    client, provider = _client(ProviderFixture())
    provider.identity["email"] = None
    with client:
        state, _ = _begin_login(client)
        response = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        cookie = response.headers["set-cookie"].lower()
        assert "oidc_session=" in cookie
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=lax" in cookie
        assert "path=/" in cookie
        raw_token = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        client.cookies.set("oidc_session", raw_token)
        session_response = client.get("/api/v1/auth/session")
        assert session_response.status_code == 200
        assert session_response.headers["cache-control"] == "no-store"
        assert session_response.json()["user"] == {
            "oid": "employee-object-id",
            "upn": "employee@infovision.example",
            "email": None,
            "name": "InfoVision Employee",
        }
        with client.app.state.session_factory() as session:
            record = session.query(OidcApplicationSession).one()
            assert record.token_digest != raw_token
            assert record.email is None


def test_missing_email_does_not_block_callback() -> None:
    client, provider = _client(ProviderFixture())
    provider.identity.pop("email")
    with client:
        state, _ = _begin_login(client)
        response = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        with client.app.state.session_factory() as session:
            assert session.query(OidcApplicationSession).one().email is None


def test_provider_error_is_generic_and_consumes_transaction() -> None:
    client, _ = _client(ProviderFixture())
    with client:
        state, _ = _begin_login(client)
        response = client.get(
            "/api/v1/auth/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/?auth=error"
        assert "access_denied" not in response.text
        with client.app.state.session_factory() as session:
            assert session.query(OidcLoginTransaction).count() == 0
            assert session.query(OidcApplicationSession).count() == 0


def test_missing_required_claims_and_invalid_tokens_never_create_session() -> None:
    for reason in (
        "invalid signature",
        "invalid issuer",
        "invalid audience",
        "expired token",
        "nonce mismatch",
        "PKCE failure",
        "missing required claim",
    ):
        provider = ProviderFixture()
        provider.failure = reason
        client, _ = _client(provider)
        with client:
            state, _ = _begin_login(client)
            response = client.get(
                "/api/v1/auth/callback",
                params={"code": "synthetic-code", "state": state},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/?auth=error"
            with client.app.state.session_factory() as session:
                assert session.query(OidcApplicationSession).count() == 0


def test_state_mismatch_and_replay_cannot_create_session() -> None:
    client, _ = _client(ProviderFixture())
    with client:
        state, _ = _begin_login(client)
        mismatch = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": "not-the-state"},
        )
        successful = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
            follow_redirects=False,
        )
        replay = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
        )
        assert mismatch.status_code == 401
        assert successful.status_code == 303
        assert replay.status_code == 401
        with client.app.state.session_factory() as session:
            assert session.query(OidcApplicationSession).count() == 1


def test_auth_logs_do_not_include_callback_values(caplog) -> None:
    client, _ = _client(ProviderFixture())
    sentinels = ("synthetic-code", "synthetic-state-value", "synthetic-token-value")
    with client, caplog.at_level(logging.DEBUG, logger="aimplify_intake"):
        state, _ = _begin_login(client)
        client.get(
            "/api/v1/auth/callback",
            params={"code": sentinels[0], "state": state},
            follow_redirects=False,
        )
    assert all(value not in caplog.text for value in sentinels)


def test_entra_provider_validates_signature_registered_claims_and_profile(monkeypatch) -> None:
    def rsa_key_pair():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return import_key(private_pem, key_type="RSA"), import_key(
            public_pem, key_type="RSA"
        )

    signing_key, public_jwk = rsa_key_pair()
    wrong_signing_key, _ = rsa_key_pair()
    public_key = public_jwk.as_dict()
    public_key["kid"] = "entra-test-key"
    token_holder = {"value": ""}

    class FakeOAuthClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def fetch_token(self, *_args, **_kwargs):
            return {"id_token": token_holder["value"]}

        async def aclose(self) -> None:
            return None

    class FakeResponse:
        def __init__(self, value) -> None:
            self.value = value

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.value

    class FakeHttpClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, _url: str):
            return FakeResponse({"keys": [public_key]})

    settings = AuthSettings(
        tenant_id="test-tenant",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
        redirect_uri="https://app.example.test/api/v1/auth/callback",
        post_logout_redirect_uri="https://app.example.test/",
        auth_required=True,
        app_env="test",
        mock_mode=False,
    )
    provider = EntraOidcProvider(settings)
    provider._metadata = {
        "issuer": "https://issuer.example.test",
        "token_endpoint": "https://issuer.example.test/token",
        "jwks_uri": "https://issuer.example.test/keys",
        "authorization_endpoint": "https://issuer.example.test/authorize",
        "end_session_endpoint": "https://issuer.example.test/logout",
    }
    verifier = "test-pkce-verifier"
    authorization_url = asyncio.run(
        provider.authorization_url(
            state="test-state",
            nonce="test-nonce",
            pkce_verifier=verifier,
        )
    )
    authorization_query = parse_qs(urlsplit(authorization_url).query)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert authorization_query["state"] == ["test-state"]
    assert authorization_query["nonce"] == ["test-nonce"]
    assert authorization_query["code_challenge_method"] == ["S256"]
    assert authorization_query["code_challenge"] == [expected_challenge]
    monkeypatch.setattr(auth_module, "AsyncOAuth2Client", FakeOAuthClient)
    monkeypatch.setattr(auth_module.httpx, "AsyncClient", FakeHttpClient)

    def make_token(claim_overrides=None, key=signing_key, kid="entra-test-key"):
        now = int(time.time())
        claims = {
            "iss": "https://issuer.example.test",
            "aud": "synthetic-client",
            "sub": "synthetic-subject",
            "exp": now + 300,
            "iat": now,
            "nonce": "expected-nonce",
            "oid": "employee-object-id",
            "upn": "employee@infovision.example",
            "name": "InfoVision Employee",
        }
        claims.update(claim_overrides or {})
        return jwt.encode({"alg": "RS256", "kid": kid}, claims, key, algorithms=["RS256"])

    async def validate(token: str):
        token_holder["value"] = token
        return await provider.validate_authorization_code(
            code="synthetic-code",
            nonce="expected-nonce",
            pkce_verifier="synthetic-verifier",
        )

    assert asyncio.run(validate(make_token())) == {
        "oid": "employee-object-id",
        "upn": "employee@infovision.example",
        "name": "InfoVision Employee",
        "email": None,
    }
    invalid_tokens = [
        make_token(key=wrong_signing_key, kid="other-test-key"),
        make_token({"iss": "https://wrong-issuer.example.test"}),
        make_token({"aud": "wrong-client"}),
        make_token({"exp": int(time.time()) - 120}),
        make_token({"nonce": "wrong-nonce"}),
        make_token({"upn": None}),
    ]
    for index, token in enumerate(invalid_tokens):
        try:
            asyncio.run(validate(token))
        except OidcProviderError:
            continue
        pytest.fail(f"invalid ID token {index} was accepted")


def test_logout_revokes_local_session_clears_cookie_and_redirects() -> None:
    client, _provider = _client(ProviderFixture())
    with client:
        state, _ = _begin_login(client)
        login = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
            follow_redirects=False,
        )
        raw_token = login.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        client.cookies.set("oidc_session", raw_token)
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"origin": "http://testserver"},
            follow_redirects=False,
        )
        assert logout.status_code == 303
        assert logout.headers["location"] == (
            "https://login.example.test/logout?client_id=synthetic-client"
        )
        cookie = logout.headers["set-cookie"].lower()
        assert "oidc_session=" in cookie
        assert "max-age=0" in cookie
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=lax" in cookie
        with client.app.state.session_factory() as session:
            record = session.query(OidcApplicationSession).one()
            assert record.revoked_at is not None
        assert client.get("/api/v1/auth/session").status_code == 401


def test_logout_rejects_untrusted_origin_and_is_idempotent() -> None:
    client, _ = _client(ProviderFixture())
    with client:
        denied = client.post(
            "/api/v1/auth/logout",
            headers={"origin": "https://attacker.invalid"},
            follow_redirects=False,
        )
        assert denied.status_code == 403
        response = client.post(
            "/api/v1/auth/logout",
            headers={"origin": "http://testserver"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("https://login.example.test/logout")


def test_logout_still_revokes_and_clears_cookie_when_provider_is_unavailable() -> None:
    provider = ProviderFixture()
    provider.logout_failure = True
    client, _ = _client(provider)
    with client:
        state, _ = _begin_login(client)
        login = client.get(
            "/api/v1/auth/callback",
            params={"code": "synthetic-code", "state": state},
            follow_redirects=False,
        )
        raw_token = login.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
        client.cookies.set("oidc_session", raw_token)
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"origin": "http://testserver"},
            follow_redirects=False,
        )
        assert logout.status_code == 303
        assert logout.headers["location"] == "/?auth=error"
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        with client.app.state.session_factory() as session:
            assert session.query(OidcApplicationSession).one().revoked_at is not None
