from datetime import UTC, datetime, timedelta

from aimplify_intake.persistence.models import OidcApplicationSession, OidcLoginTransaction
from aimplify_intake.persistence.repositories import (
    consume_oidc_transaction,
    create_database,
    create_oidc_session,
    create_oidc_transaction,
    get_active_oidc_session,
    purge_expired_oidc_transactions,
    revoke_oidc_session,
)


def _session_factory():
    _, factory = create_database("sqlite+pysqlite:///:memory:")
    return factory


def test_login_transaction_is_consumed_once() -> None:
    factory = _session_factory()
    now = datetime.now(UTC)
    with factory() as session:
        transaction = create_oidc_transaction(
            session,
            state="state-value",
            nonce="nonce-value",
            pkce_verifier="verifier-value",
            now=now,
        )
        assert transaction.state_digest != "state-value"
        transaction_id = transaction.transaction_id

    with factory() as session:
        consumed = consume_oidc_transaction(session, "state-value", now=now)
        assert consumed is not None
        assert consumed.transaction_id == transaction_id
        assert consumed.nonce == "nonce-value"
        assert consumed.pkce_verifier == "verifier-value"

    with factory() as session:
        assert consume_oidc_transaction(session, "state-value", now=now) is None


def test_expired_login_transaction_cannot_be_consumed_and_is_purged() -> None:
    factory = _session_factory()
    now = datetime.now(UTC)
    with factory() as session:
        create_oidc_transaction(
            session,
            state="expired-state",
            nonce="nonce-value",
            pkce_verifier="verifier-value",
            expires_at=now - timedelta(seconds=1),
            now=now - timedelta(minutes=11),
        )

    with factory() as session:
        assert consume_oidc_transaction(session, "expired-state", now=now) is None
        assert purge_expired_oidc_transactions(session, now=now) == 1
        assert session.query(OidcLoginTransaction).count() == 0


def test_session_uses_token_digest_and_rejects_expiry_and_revocation() -> None:
    factory = _session_factory()
    raw_token = "opaque-session-token"
    now = datetime.now(UTC)
    profile = {"oid": "employee-oid", "upn": "employee@example.test", "email": None, "name": "Employee"}
    with factory() as session:
        record = create_oidc_session(
            session,
            raw_token,
            profile,
            expires_at=now + timedelta(hours=1),
            now=now,
        )
        assert record.token_digest != raw_token
        assert get_active_oidc_session(session, raw_token, now=now).subject_ref == "employee-oid"

    with factory() as session:
        record = get_active_oidc_session(session, raw_token, now=now)
        assert record is not None
        record.expires_at = now - timedelta(seconds=1)
        session.commit()
        assert get_active_oidc_session(session, raw_token, now=now) is None

    with factory() as session:
        record = get_active_oidc_session(session, raw_token, now=now + timedelta(hours=2))
        assert record is None


def test_revoked_session_is_not_resolved() -> None:
    factory = _session_factory()
    raw_token = "another-session-token"
    with factory() as session:
        create_oidc_session(
            session,
            raw_token,
            {"oid": "employee-oid", "upn": "employee@example.test", "email": None, "name": "Employee"},
        )

    with factory() as session:
        assert revoke_oidc_session(session, raw_token)
        assert get_active_oidc_session(session, raw_token) is None

    with factory() as session:
        assert not revoke_oidc_session(session, raw_token)


def test_session_email_is_nullable_and_digest_is_unique() -> None:
    factory = _session_factory()
    with factory() as session:
        record = create_oidc_session(
            session,
            "session-one",
            {"oid": "employee-oid", "upn": "employee@example.test", "email": None, "name": "Employee"},
        )
        assert record.email is None
        assert record.token_digest
        assert session.query(OidcApplicationSession).count() == 1
