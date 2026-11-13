"""OIDC configuration, provider validation, and local-session identity resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from sqlalchemy.orm import sessionmaker

from aimplify_intake.persistence.repositories import get_active_oidc_session


class AuthConfigurationError(ValueError):
    """Raised when authentication runtime settings are incomplete or unsafe."""


class OidcProviderError(ValueError):
    """Raised when the identity provider response cannot be trusted."""


@dataclass(frozen=True)
class AuthSettings:
    tenant_id: str | None
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    post_logout_redirect_uri: str | None
    auth_required: bool
    app_env: str
    mock_mode: bool

    @property
    def discovery_url(self) -> str | None:
        if not self.tenant_id:
            return None
        tenant = quote(self.tenant_id, safe="")
        return (
            "https://login.microsoftonline.com/"
            f"{tenant}/v2.0/.well-known/openid-configuration"
        )


def _read_bool(environment: Mapping[str, str], key: str, default: bool) -> bool:
    value = environment.get(key)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise AuthConfigurationError(f"{key} must be true or false.")


def load_auth_settings(
    environment: Mapping[str, str] | None = None,
) -> AuthSettings:
    values = environment if environment is not None else os.environ
    app_env = values.get("APP_ENV", "local").strip().lower()
    if not app_env:
        raise AuthConfigurationError("APP_ENV cannot be empty.")

    tenant_id = values.get("AZURE_AD_TENANT_ID") or None
    settings = AuthSettings(
        tenant_id=tenant_id,
        client_id=values.get("AZURE_AD_CLIENT_ID") or None,
        client_secret=values.get("AZURE_AD_CLIENT_SECRET") or None,
        redirect_uri=values.get("AZURE_AD_REDIRECT_URI") or None,
        post_logout_redirect_uri=values.get("AZURE_AD_POST_LOGOUT_REDIRECT_URI") or None,
        auth_required=_read_bool(values, "AUTH_REQUIRED", False),
        app_env=app_env,
        mock_mode=_read_bool(values, "AUTH_MOCK_MODE", False),
    )

    if settings.mock_mode and (
        settings.app_env not in {"local", "test"} or settings.tenant_id is not None
    ):
        raise AuthConfigurationError(
            "AUTH_MOCK_MODE is allowed only in local/test without an Entra tenant."
        )
    if settings.app_env == "demo" and settings.auth_required:
        raise AuthConfigurationError("Demo deployments must set AUTH_REQUIRED=false.")
    if settings.app_env == "production" and not settings.auth_required:
        raise AuthConfigurationError("Production requires AUTH_REQUIRED=true.")
    if settings.app_env == "production" and settings.auth_required:
        missing = [
            name
            for name, value in (
                ("AZURE_AD_TENANT_ID", settings.tenant_id),
                ("AZURE_AD_CLIENT_ID", settings.client_id),
                ("AZURE_AD_CLIENT_SECRET", settings.client_secret),
                ("AZURE_AD_REDIRECT_URI", settings.redirect_uri),
                ("AZURE_AD_POST_LOGOUT_REDIRECT_URI", settings.post_logout_redirect_uri),
            )
            if not value
        ]
        if missing:
            raise AuthConfigurationError(
                "Production authentication configuration is incomplete: "
                + ", ".join(missing)
                + "."
            )
        if not settings.redirect_uri.startswith("https://") or not settings.post_logout_redirect_uri.startswith(
            "https://"
        ):
            raise AuthConfigurationError(
                "Production authentication redirect URLs must use HTTPS."
            )
    return settings


def create_identity_verifier(session_factory: sessionmaker[Any]):
    """Resolve an opaque application cookie to a validated employee identity."""

    def verify(raw_token: str) -> dict[str, Any]:
        with session_factory() as session:
            record = get_active_oidc_session(session, raw_token)
            if record is None:
                raise ValueError("Unauthenticated.")
            return {
                "subject": record.subject_ref,
                "oid": record.subject_ref,
                "upn": record.upn,
                "email": record.email,
                "name": record.name,
            }

    return verify


class EntraOidcProvider:
    """Authlib-backed authorization-code client for one Entra tenant."""

    def __init__(self, settings: AuthSettings) -> None:
        if not all(
            (
                settings.tenant_id,
                settings.client_id,
                settings.client_secret,
                settings.redirect_uri,
                settings.discovery_url,
            )
        ):
            raise AuthConfigurationError("OIDC provider configuration is incomplete.")
        self.settings = settings
        self._metadata: dict[str, Any] | None = None

    async def _get_metadata(self) -> dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        if self.settings.discovery_url is None:
            raise AuthConfigurationError("OIDC discovery is not configured.")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.settings.discovery_url)
            response.raise_for_status()
            metadata = response.json()
        if (
            not isinstance(metadata, dict)
            or not isinstance(metadata.get("issuer"), str)
            or not isinstance(metadata.get("authorization_endpoint"), str)
            or not isinstance(metadata.get("token_endpoint"), str)
            or not isinstance(metadata.get("jwks_uri"), str)
            or not isinstance(metadata.get("end_session_endpoint"), str)
        ):
            raise OidcProviderError("OIDC discovery metadata is incomplete.")
        for endpoint in (
            metadata["authorization_endpoint"],
            metadata["token_endpoint"],
            metadata["jwks_uri"],
            metadata["end_session_endpoint"],
        ):
            if not endpoint.startswith("https://"):
                raise OidcProviderError("OIDC endpoints must use HTTPS.")
        self._metadata = metadata
        return metadata

    async def authorization_url(
        self, *, state: str, nonce: str, pkce_verifier: str
    ) -> str:
        metadata = await self._get_metadata()
        client = AsyncOAuth2Client(
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            redirect_uri=self.settings.redirect_uri,
            scope="openid profile email",
            code_challenge_method="S256",
            token_endpoint_auth_method="client_secret_post",
        )
        try:
            url, _ = client.create_authorization_url(
                metadata["authorization_endpoint"],
                state=state,
                nonce=nonce,
                code_verifier=pkce_verifier,
            )
            return url
        finally:
            await client.aclose()

    async def validate_authorization_code(
        self, *, code: str, nonce: str, pkce_verifier: str
    ) -> dict[str, str | None]:
        metadata = await self._get_metadata()
        client = AsyncOAuth2Client(
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            redirect_uri=self.settings.redirect_uri,
            scope="openid profile email",
            code_challenge_method="S256",
            token_endpoint_auth_method="client_secret_post",
        )
        try:
            token = await client.fetch_token(
                metadata["token_endpoint"],
                code=code,
                code_verifier=pkce_verifier,
                redirect_uri=self.settings.redirect_uri,
            )
        finally:
            await client.aclose()
        raw_id_token = token.get("id_token")
        if not isinstance(raw_id_token, str):
            raise OidcProviderError("The provider did not return an ID token.")

        async with httpx.AsyncClient(timeout=10) as http_client:
            key_response = await http_client.get(metadata["jwks_uri"])
            key_response.raise_for_status()
            key_set = KeySet.import_key_set(key_response.json())
        try:
            claims = jwt.decode(raw_id_token, key_set, algorithms=["RS256"]).claims
        except (JoseError, ValueError, TypeError) as error:
            raise OidcProviderError("The ID token could not be validated.") from error

        now = datetime.now(UTC).timestamp()
        expiry = claims.get("exp")
        not_before = claims.get("nbf")
        issued_at = claims.get("iat")
        if (
            isinstance(expiry, bool)
            or not isinstance(expiry, (int, float))
            or expiry <= now - 60
            or (
                not_before is not None
                and (
                    isinstance(not_before, bool)
                    or not isinstance(not_before, (int, float))
                    or not_before > now + 60
                )
            )
            or (
                issued_at is not None
                and (
                    isinstance(issued_at, bool)
                    or not isinstance(issued_at, (int, float))
                    or issued_at > now + 60
                )
            )
        ):
            raise OidcProviderError("The ID token is expired or not yet valid.")

        audience = claims.get("aud")
        valid_audience = (
            audience == self.settings.client_id
            if isinstance(audience, str)
            else isinstance(audience, list) and self.settings.client_id in audience
        )
        if claims.get("iss") != metadata["issuer"] or not valid_audience:
            raise OidcProviderError("The ID token issuer or audience is invalid.")
        if (
            isinstance(audience, list)
            and len(audience) > 1
            and claims.get("azp") != self.settings.client_id
        ):
            raise OidcProviderError("The ID token authorized party is invalid.")
        if claims.get("nonce") != nonce:
            raise OidcProviderError("The ID token nonce is invalid.")

        identity: dict[str, str | None] = {}
        for claim, target in (("oid", "oid"), ("upn", "upn"), ("name", "name")):
            value = claims.get(claim)
            if not isinstance(value, str) or not value.strip():
                raise OidcProviderError("A required employee claim is missing.")
            identity[target] = value
        email = claims.get("email")
        if email is not None and not isinstance(email, str):
            raise OidcProviderError("The employee email claim is invalid.")
        identity["email"] = email or None
        return identity

    async def logout_url(self) -> str:
        from urllib.parse import urlencode

        metadata = await self._get_metadata()
        endpoint = metadata["end_session_endpoint"]
        query = urlencode(
            {
                "client_id": self.settings.client_id,
                "post_logout_redirect_uri": self.settings.post_logout_redirect_uri,
            }
        )
        return f"{endpoint}{'&' if '?' in endpoint else '?'}{query}"


def validate_oidc_claims(
    claims: dict[str, Any], *, expected_issuer: str, expected_audience: str
) -> dict[str, Any]:
    """Validate standard identity constraints for already signature-verified claims."""
    issuer = claims.get("iss")
    audience = claims.get("aud")
    subject = claims.get("sub")
    expiry = claims.get("exp")

    if issuer != expected_issuer:
        raise ValueError("Invalid OIDC issuer.")
    if not subject:
        raise ValueError("OIDC subject is required.")
    if isinstance(audience, str):
        valid_audience = audience == expected_audience
    else:
        valid_audience = isinstance(audience, list) and expected_audience in audience
    if not valid_audience:
        raise ValueError("Invalid OIDC audience.")

    now_epoch = int(datetime.now(tz=UTC).timestamp())
    if not isinstance(expiry, int) or expiry <= now_epoch:
        raise ValueError("OIDC token is expired.")

    return {"subject": subject}
