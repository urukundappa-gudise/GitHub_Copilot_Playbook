"""Transactional persistence operations for intake sessions and safe values."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aimplify_intake.persistence.models import (
    Base,
    CanonicalFieldDefinition,
    FieldValue,
    IdeaSubmission,
    IntakeSection,
    OidcApplicationSession,
    OidcLoginTransaction,
    SchemaVersion,
)
from aimplify_intake.safety.no_facts import is_no_facts_validated
from aimplify_intake.schema.registry import load_canonical_schema, publish_schema
from aimplify_intake.schema.validation import (
    validate_field_origin,
    validate_field_policy,
    validate_field_value,
)

NON_AI_WRITABLE = {"declaration_accepted", "submitter_signature", "date_of_submission", "reviewer_notes"}
OIDC_TRANSACTION_TTL_SECONDS = 600
OIDC_SESSION_TTL_SECONDS = 8 * 60 * 60


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_oidc_transaction(
    session: Session,
    *,
    state: str,
    nonce: str,
    pkce_verifier: str,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> OidcLoginTransaction:
    created_at = now or datetime.now(UTC)
    transaction = OidcLoginTransaction(
        transaction_id=uuid4().hex,
        state_digest=_digest(state),
        nonce=nonce,
        pkce_verifier=pkce_verifier,
        created_at=created_at,
        expires_at=expires_at or created_at + timedelta(seconds=OIDC_TRANSACTION_TTL_SECONDS),
    )
    session.add(transaction)
    session.commit()
    return transaction


def consume_oidc_transaction(
    session: Session, state: str, *, now: datetime | None = None
) -> OidcLoginTransaction | None:
    consumed_at = now or datetime.now(UTC)
    state_digest = _digest(state)
    try:
        result = session.execute(
            update(OidcLoginTransaction)
            .where(
                OidcLoginTransaction.state_digest == state_digest,
                OidcLoginTransaction.expires_at > consumed_at,
                OidcLoginTransaction.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
        )
        if result.rowcount != 1:
            session.rollback()
            return None
        transaction = session.scalar(
            select(OidcLoginTransaction).where(
                OidcLoginTransaction.state_digest == state_digest
            )
        )
        if transaction is None:
            session.rollback()
            return None
        session.delete(transaction)
        session.commit()
        return transaction
    except Exception:
        session.rollback()
        raise


def purge_expired_oidc_transactions(
    session: Session, *, now: datetime | None = None
) -> int:
    cutoff = now or datetime.now(UTC)
    try:
        result = session.execute(
            delete(OidcLoginTransaction).where(
                (OidcLoginTransaction.expires_at <= cutoff)
                | OidcLoginTransaction.consumed_at.is_not(None)
            )
        )
        session.commit()
        return int(result.rowcount or 0)
    except Exception:
        session.rollback()
        raise


def create_oidc_session(
    session: Session,
    raw_token: str,
    identity: dict[str, object],
    *,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> OidcApplicationSession:
    created_at = now or datetime.now(UTC)
    subject = identity.get("oid")
    upn = identity.get("upn")
    name = identity.get("name")
    email = identity.get("email")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("A verified employee object identifier is required.")
    if not isinstance(upn, str) or not upn.strip():
        raise ValueError("A verified employee sign-in name is required.")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A verified employee display name is required.")
    if email is not None and not isinstance(email, str):
        raise ValueError("The verified employee email must be text or null.")
    record = OidcApplicationSession(
        session_id=uuid4().hex,
        token_digest=_digest(raw_token),
        subject_ref=subject,
        upn=upn,
        email=email,
        name=name,
        created_at=created_at,
        expires_at=expires_at
        or created_at + timedelta(seconds=OIDC_SESSION_TTL_SECONDS),
    )
    session.add(record)
    session.commit()
    return record


def get_active_oidc_session(
    session: Session, raw_token: str, *, now: datetime | None = None
) -> OidcApplicationSession | None:
    current_time = now or datetime.now(UTC)
    return session.scalar(
        select(OidcApplicationSession).where(
            OidcApplicationSession.token_digest == _digest(raw_token),
            OidcApplicationSession.expires_at > current_time,
            OidcApplicationSession.revoked_at.is_(None),
        )
    )


def revoke_oidc_session(
    session: Session, raw_token: str, *, now: datetime | None = None
) -> bool:
    revoked_at = now or datetime.now(UTC)
    try:
        result = session.execute(
            update(OidcApplicationSession)
            .where(
                OidcApplicationSession.token_digest == _digest(raw_token),
                OidcApplicationSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        session.commit()
        return result.rowcount == 1
    except Exception:
        session.rollback()
        raise


def create_database(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def ensure_canonical_schema(session: Session) -> None:
    schema = publish_schema(load_canonical_schema())
    if session.get(SchemaVersion, schema.schema_version) is not None:
        return
    session.add(
        SchemaVersion(
            schema_version=schema.schema_version,
            published_at=datetime.now(UTC),
            field_count=len(schema.fields),
            section_count=len(schema.sections),
            mandatory_count=sum(bool(field["mandatory"]) for field in schema.fields),
        )
    )
    session.add_all(
        IntakeSection(
            schema_version=schema.schema_version,
            section_key=section["key"],
            name=section["name"],
            ordinal=section["ordinal"],
        )
        for section in schema.sections
    )
    session.add_all(
        CanonicalFieldDefinition(
            schema_version=schema.schema_version,
            field_key=field["key"],
            display_name=field["display_name"],
            section_key=field["section_key"],
            value_type=field["value_type"],
            mandatory=field["mandatory"],
            fill_mode=field["fill_mode"],
            ai_writable=field["ai_writable"],
            declaration_only=field["declaration_only"],
            clarification_prompt=field["clarification_prompt"],
        )
        for field in schema.fields
    )
    session.commit()


def create_submission(session: Session, subject_ref: str) -> IdeaSubmission:
    ensure_canonical_schema(session)
    submission = IdeaSubmission(
        submission_id=uuid4().hex,
        schema_version="active",
        subject_ref=subject_ref,
        status="in_progress",
    )
    session.add(submission)
    session.commit()
    return submission


def get_authorized_submission(session: Session, submission_id: str, subject_ref: str) -> IdeaSubmission | None:
    submission = session.get(IdeaSubmission, submission_id)
    if submission is None or submission.subject_ref != subject_ref:
        return None
    return submission


def read_field_state(session: Session, submission: IdeaSubmission) -> dict[str, object]:
    schema = publish_schema(load_canonical_schema())
    values = {
        item.field_key: item
        for item in session.scalars(
            select(FieldValue).where(FieldValue.submission_id == submission.submission_id)
        )
    }
    sections = []
    for section in schema.sections:
        fields = []
        for definition in schema.fields:
            if definition["section_key"] != section["key"]:
                continue
            value = values.get(definition["key"])
            validate_field_policy(definition)
            field_state: dict[str, object] = {
                "field_key": definition["key"],
                "mandatory": definition["mandatory"],
                "human_only": not definition["ai_writable"],
            }
            if value is not None and (
                definition["ai_writable"] or value.origin == "human_entered"
            ):
                field_state.update({"value": value.value, "origin": value.origin})
            fields.append(field_state)
        sections.append({"section_key": section["key"], "fields": fields})
    return {
        "session_id": submission.submission_id,
        "schema_version": submission.schema_version,
        "sections": sections,
        "status": submission.status,
    }


def persist_ai_values(session: Session, submission: IdeaSubmission, updates: list[dict[str, str]]) -> None:
    schema = publish_schema(load_canonical_schema())
    definitions = {field["key"]: field for field in schema.fields}
    validated = []
    for candidate_update in updates:
        field_key = candidate_update["field_key"]
        definition = definitions.get(field_key)
        if definition is None or field_key in NON_AI_WRITABLE:
            raise ValueError("Candidate field is not AI-writable.")
        validate_field_origin(definition, "ai_extracted")
        if not is_no_facts_validated(candidate_update):
            raise ValueError("AI candidate has not passed NoFacts validation.")
        validated.append(
            (field_key, validate_field_value(definition, candidate_update["value"]))
        )
    try:
        for field_key, value in validated:
            current = session.scalar(
                select(FieldValue).where(
                    FieldValue.submission_id == submission.submission_id,
                    FieldValue.field_key == field_key,
                )
            )
            if current is None:
                session.add(
                    FieldValue(
                        submission_id=submission.submission_id,
                        field_key=field_key,
                        value=value,
                        origin="ai_extracted",
                    )
                )
            else:
                current.value = value
                current.origin = "ai_extracted"
                current.updated_at = datetime.now(UTC)
        session.commit()
    except Exception:
        session.rollback()
        raise


def persist_human_values(
    session: Session, submission: IdeaSubmission, updates: dict[str, object]
) -> dict[str, str]:
    schema = publish_schema(load_canonical_schema())
    definitions = {field["key"]: field for field in schema.fields}
    validated: dict[str, str] = {}
    for field_key, candidate in updates.items():
        definition = definitions.get(field_key)
        if definition is None:
            raise ValueError("Candidate field is not human-entry-only.")
        validate_field_origin(definition, "human_entered")
        validated[field_key] = validate_field_value(definition, candidate)
    try:
        for field_key, value in validated.items():
            current = session.scalar(
                select(FieldValue).where(
                    FieldValue.submission_id == submission.submission_id,
                    FieldValue.field_key == field_key,
                )
            )
            if current is None:
                session.add(
                    FieldValue(
                        submission_id=submission.submission_id,
                        field_key=field_key,
                        value=value,
                        origin="human_entered",
                    )
                )
            else:
                current.value = value
                current.origin = "human_entered"
                current.updated_at = datetime.now(UTC)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return validated