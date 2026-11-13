"""Store one-use OIDC login transactions and revocable application sessions.

Revision ID: 0003_oidc_sessions
Revises: 0002_human_only_field_constraints
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_oidc_sessions"
down_revision = "0002_human_only_field_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oidc_login_transactions",
        sa.Column("transaction_id", sa.String(length=64), primary_key=True),
        sa.Column("state_digest", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=255), nullable=False),
        sa.Column("pkce_verifier", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(state_digest) > 0", name="ck_oidc_transaction_state_digest"),
        sa.CheckConstraint("length(nonce) > 0", name="ck_oidc_transaction_nonce"),
        sa.CheckConstraint(
            "length(pkce_verifier) > 0", name="ck_oidc_transaction_pkce_verifier"
        ),
        sa.UniqueConstraint("state_digest", name="uq_oidc_login_transactions_state_digest"),
    )
    op.create_table(
        "oidc_application_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("subject_ref", sa.String(length=255), nullable=False),
        sa.Column("upn", sa.String(length=320), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(token_digest) > 0", name="ck_oidc_session_token_digest"),
        sa.CheckConstraint("length(subject_ref) > 0", name="ck_oidc_session_subject"),
        sa.CheckConstraint("length(upn) > 0", name="ck_oidc_session_upn"),
        sa.CheckConstraint("length(name) > 0", name="ck_oidc_session_name"),
        sa.UniqueConstraint("token_digest", name="uq_oidc_application_sessions_token_digest"),
    )


def downgrade() -> None:
    op.drop_table("oidc_application_sessions")
    op.drop_table("oidc_login_transactions")
