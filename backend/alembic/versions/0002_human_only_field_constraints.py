"""Constrain declaration metadata to human-only writes.

Revision ID: 0002_human_only_field_constraints
Revises: 0001_phase2_foundation
Create Date: 2026-11-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_human_only_field_constraints"
down_revision = "0001_phase2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision ID exceeds Alembic's default 32-character version column.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_declaration_fields_not_ai_writable",
        "canonical_field_definitions",
        "NOT declaration_only OR NOT ai_writable",
    )
    op.create_check_constraint(
        "ck_human_only_fields_not_ai_writable",
        "canonical_field_definitions",
        "fill_mode != 'Human only' OR NOT ai_writable",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_human_only_fields_not_ai_writable",
        "canonical_field_definitions",
        type_="check",
    )
    op.drop_constraint(
        "ck_declaration_fields_not_ai_writable",
        "canonical_field_definitions",
        type_="check",
    )