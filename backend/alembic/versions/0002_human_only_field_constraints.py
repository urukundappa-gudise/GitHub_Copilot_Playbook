"""Constrain declaration metadata to human-only writes.

Revision ID: 0002_human_only_field_constraints
Revises: 0001_phase2_foundation
Create Date: 2026-11-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_human_only_field_constraints"
down_revision = "0001_phase2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("alembic_version", "version_num", type_=sa.String(64))
    with op.batch_alter_table("canonical_field_definitions") as batch_op:
        batch_op.create_check_constraint(
            "ck_declaration_fields_not_ai_writable",
            "NOT declaration_only OR NOT ai_writable",
        )
        batch_op.create_check_constraint(
            "ck_human_only_fields_not_ai_writable",
            "fill_mode != 'Human only' OR NOT ai_writable",
        )


def downgrade() -> None:
    with op.batch_alter_table("canonical_field_definitions") as batch_op:
        batch_op.drop_constraint("ck_human_only_fields_not_ai_writable", type_="check")
        batch_op.drop_constraint("ck_declaration_fields_not_ai_writable", type_="check")