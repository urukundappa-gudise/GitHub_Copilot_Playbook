"""Transactional persistence operations for intake sessions and safe values."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aimplify_intake.persistence.models import (
    Base,
    CanonicalFieldDefinition,
    FieldValue,
    IdeaSubmission,
    IntakeSection,
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


def _ordered_canonical_keys(keys: Iterable[str]) -> list[str]:
    requested = set(keys)
    schema = publish_schema(load_canonical_schema())
    return [field["key"] for field in schema.fields if field["key"] in requested]


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class SubmissionPersistenceError(Exception):
    code: str
    status_code: int

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SubmissionIncompleteError(SubmissionPersistenceError):
    code = "SUBMISSION_INCOMPLETE"
    status_code = 422

    def __init__(self, missing_fields: Iterable[str], invalid_fields: Iterable[str]) -> None:
        self.missing_fields = _ordered_canonical_keys(missing_fields)
        self.invalid_fields = _ordered_canonical_keys(invalid_fields)
        super().__init__(
            "Complete the required information and save your declaration before submitting."
        )


class SubmissionClosedError(SubmissionPersistenceError):
    code = "SUBMISSION_CLOSED"
    status_code = 409

    def __init__(self) -> None:
        super().__init__("This idea has already been submitted.")


class SubmissionNotFoundError(SubmissionPersistenceError):
    code = "SESSION_NOT_FOUND"
    status_code = 404

    def __init__(self) -> None:
        super().__init__("Session not found.")


class SubmissionUnavailableError(SubmissionPersistenceError):
    code = "SERVICE_UNAVAILABLE"
    status_code = 503

    def __init__(self) -> None:
        super().__init__("The intake service is temporarily unavailable.")


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
    session.flush()
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


def get_submission_readiness(session: Session, submission: IdeaSubmission) -> dict[str, object]:
    schema = publish_schema(load_canonical_schema())
    stored_values = {
        item.field_key: item
        for item in session.scalars(
            select(FieldValue)
            .where(FieldValue.submission_id == submission.submission_id)
            .execution_options(populate_existing=True)
        )
    }
    declaration_keys = {"declaration_accepted", "date_of_submission", "submitter_signature"}
    required_fields = [
        field for field in schema.fields if field["mandatory"] or field["key"] in declaration_keys
    ]
    missing_fields: list[str] = []
    invalid_fields: list[str] = []

    for definition in required_fields:
        field_key = definition["key"]
        stored = stored_values.get(field_key)
        if stored is None:
            missing_fields.append(field_key)
            continue

        try:
            validate_field_origin(definition, stored.origin)
            candidate: object = stored.value
            if definition["value_type"] == "boolean":
                if stored.value not in {"true", "false"}:
                    raise ValueError("Stored boolean is invalid.")
                candidate = stored.value == "true"
            validate_field_value(definition, candidate)
            if field_key in declaration_keys and stored.origin != "human_entered":
                raise ValueError("Declaration origin is invalid.")
            if field_key == "declaration_accepted" and stored.value != "true":
                raise ValueError("Declaration acceptance is required.")
        except ValueError:
            invalid_fields.append(field_key)

    if submission.status == "submitted":
        return {"ready": True, "missing_fields": [], "invalid_fields": []}
    return {
        "ready": not missing_fields and not invalid_fields,
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
    }


def _lock_submission_for_write(
    session: Session, submission_id: str, subject_ref: str
) -> IdeaSubmission:
    if session.get_bind().dialect.name == "sqlite":
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        if not driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    submission = session.scalar(
        select(IdeaSubmission)
        .where(
            IdeaSubmission.submission_id == submission_id,
            IdeaSubmission.subject_ref == subject_ref,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if submission is None:
        raise SubmissionNotFoundError()
    if submission.status != "in_progress":
        raise SubmissionClosedError()
    return submission


def finalize_submission(session: Session, submission_id: str, subject_ref: str) -> dict[str, str]:
    try:
        if session.get_bind().dialect.name == "sqlite":
            connection = session.connection()
            driver_connection = connection.connection.driver_connection
            if not driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN IMMEDIATE")

        submission = session.scalar(
            select(IdeaSubmission)
            .where(
                IdeaSubmission.submission_id == submission_id,
                IdeaSubmission.subject_ref == subject_ref,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if submission is None:
            raise SubmissionNotFoundError()
        if submission.status == "submitted" and submission.submitted_at is not None:
            receipt = {
                "session_id": submission.submission_id,
                "status": "submitted",
                "submitted_at": _format_timestamp(submission.submitted_at),
            }
            session.commit()
            return receipt
        if submission.status != "in_progress":
            raise SubmissionClosedError()

        readiness = get_submission_readiness(session, submission)
        if not readiness["ready"]:
            raise SubmissionIncompleteError(
                readiness["missing_fields"], readiness["invalid_fields"]
            )

        submitted_at = datetime.now(UTC)
        submission.status = "submitted"
        submission.submitted_at = submitted_at
        submission.updated_at = submitted_at
        session.commit()
        return {
            "session_id": submission.submission_id,
            "status": "submitted",
            "submitted_at": submitted_at.isoformat(),
        }
    except SQLAlchemyError as error:
        session.rollback()
        raise SubmissionUnavailableError() from error
    except Exception:
        session.rollback()
        raise


def read_field_state(session: Session, submission: IdeaSubmission) -> dict[str, object]:
    schema = publish_schema(load_canonical_schema())
    values = {
        item.field_key: item
        for item in session.scalars(
            select(FieldValue)
            .where(FieldValue.submission_id == submission.submission_id)
            .execution_options(populate_existing=True)
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
        "submitted_at": _format_timestamp(submission.submitted_at) if submission.submitted_at else None,
        "readiness": get_submission_readiness(session, submission),
    }


def persist_ai_values(
    session: Session,
    submission: IdeaSubmission,
    updates: list[dict[str, str]],
    subject_ref: str | None = None,
) -> None:
    schema = publish_schema(load_canonical_schema())
    definitions = {field["key"]: field for field in schema.fields}
    validated = []
    for update in updates:
        field_key = update["field_key"]
        definition = definitions.get(field_key)
        if definition is None or field_key in NON_AI_WRITABLE:
            raise ValueError("Candidate field is not AI-writable.")
        validate_field_origin(definition, "ai_extracted")
        if not is_no_facts_validated(update):
            raise ValueError("AI candidate has not passed NoFacts validation.")
        validated.append((field_key, validate_field_value(definition, update["value"])))
    try:
        submission = _lock_submission_for_write(
            session,
            submission.submission_id,
            subject_ref if subject_ref is not None else submission.subject_ref,
        )
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
        session.flush()
    except SQLAlchemyError as error:
        session.rollback()
        raise SubmissionUnavailableError() from error
    except Exception:
        session.rollback()
        raise


def persist_human_values(
    session: Session,
    submission: IdeaSubmission,
    updates: dict[str, object],
    subject_ref: str | None = None,
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
        submission = _lock_submission_for_write(
            session,
            submission.submission_id,
            subject_ref if subject_ref is not None else submission.subject_ref,
        )
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
        session.flush()
    except SQLAlchemyError as error:
        session.rollback()
        raise SubmissionUnavailableError() from error
    except Exception:
        session.rollback()
        raise
    return validated