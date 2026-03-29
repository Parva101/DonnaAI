"""add_email_review_fields

Revision ID: 20260328_0004
Revises: f8de8784e5a2
Create Date: 2026-03-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260328_0004"
down_revision: Union[str, Sequence[str], None] = "f8de8784e5a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emails",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "emails",
        sa.Column("human_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("emails", "needs_review", server_default=None)


def downgrade() -> None:
    op.drop_column("emails", "human_reviewed_at")
    op.drop_column("emails", "needs_review")

