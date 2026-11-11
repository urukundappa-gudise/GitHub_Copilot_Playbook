"""Add the final-submission timestamp."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_submission_timestamp"
down_revision = "0002_human_only_field_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "idea_submissions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("idea_submissions", "submitted_at")