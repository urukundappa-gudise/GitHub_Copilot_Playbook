"""SQLAlchemy persistence models for the canonical intake schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    schema_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    field_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mandatory_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("field_count = 27", name="ck_schema_field_count"),
        CheckConstraint("section_count = 6", name="ck_schema_section_count"),
        CheckConstraint("mandatory_count = 18", name="ck_schema_mandatory_count"),
    )


class IntakeSection(Base):
    __tablename__ = "intake_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[str] = mapped_column(
        ForeignKey("schema_versions.schema_version", ondelete="CASCADE"), nullable=False
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("schema_version", "section_key", name="uq_section_key"),)


class CanonicalFieldDefinition(Base):
    __tablename__ = "canonical_field_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[str] = mapped_column(
        ForeignKey("schema_versions.schema_version", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fill_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_writable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    declaration_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    clarification_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("schema_version", "field_key", name="uq_field_key"),
        CheckConstraint(
            "NOT declaration_only OR NOT ai_writable",
            name="ck_declaration_fields_not_ai_writable",
        ),
        CheckConstraint(
            "fill_mode != 'Human only' OR NOT ai_writable",
            name="ck_human_only_fields_not_ai_writable",
        ),
    )


class IdeaSubmission(Base):
    __tablename__ = "idea_submissions"

    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[str] = mapped_column(
        ForeignKey("schema_versions.schema_version", ondelete="RESTRICT"), nullable=False
    )
    subject_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FieldValue(Base):
    __tablename__ = "field_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("idea_submissions.submission_id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("submission_id", "field_key", name="uq_submission_field"),
        CheckConstraint("origin IN ('ai_extracted','human_entered')", name="ck_field_origin"),
        CheckConstraint(
            "(field_key NOT IN ('declaration_accepted','submitter_signature','date_of_submission','reviewer_notes')) "
            "OR origin = 'human_entered'",
            name="ck_human_only_field_origin",
        ),
    )


class OidcLoginTransaction(Base):
    __tablename__ = "oidc_login_transactions"

    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    pkce_verifier: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(state_digest) > 0", name="ck_oidc_transaction_state_digest"),
        CheckConstraint("length(nonce) > 0", name="ck_oidc_transaction_nonce"),
        CheckConstraint("length(pkce_verifier) > 0", name="ck_oidc_transaction_pkce_verifier"),
    )


class OidcApplicationSession(Base):
    __tablename__ = "oidc_application_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    upn: Mapped[str] = mapped_column(String(320), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(token_digest) > 0", name="ck_oidc_session_token_digest"),
        CheckConstraint("length(subject_ref) > 0", name="ck_oidc_session_subject"),
        CheckConstraint("length(upn) > 0", name="ck_oidc_session_upn"),
        CheckConstraint("length(name) > 0", name="ck_oidc_session_name"),
    )
