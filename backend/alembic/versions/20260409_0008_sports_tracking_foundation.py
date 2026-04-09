"""sports_tracking_foundation

Revision ID: 20260409_0008
Revises: 20260409_0007
Create Date: 2026-04-09 02:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_0008"
down_revision: Union[str, Sequence[str], None] = "20260409_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sports_tracked_teams" not in tables:
        op.create_table(
            "sports_tracked_teams",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("league", sa.String(length=24), nullable=False),
            sa.Column("team_id", sa.String(length=64), nullable=False),
            sa.Column("team_name", sa.String(length=120), nullable=False),
            sa.Column("display_name", sa.String(length=160), nullable=False),
            sa.Column("abbreviation", sa.String(length=32), nullable=True),
            sa.Column("logo_url", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "league",
                "team_id",
                name="uq_sports_tracked_teams_user_league_team",
            ),
        )
        op.create_index(op.f("ix_sports_tracked_teams_user_id"), "sports_tracked_teams", ["user_id"], unique=False)
        op.create_index(op.f("ix_sports_tracked_teams_league"), "sports_tracked_teams", ["league"], unique=False)
        op.create_index(
            "ix_sports_tracked_teams_user_league",
            "sports_tracked_teams",
            ["user_id", "league"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sports_tracked_teams" in tables:
        op.drop_index("ix_sports_tracked_teams_user_league", table_name="sports_tracked_teams")
        op.drop_index(op.f("ix_sports_tracked_teams_league"), table_name="sports_tracked_teams")
        op.drop_index(op.f("ix_sports_tracked_teams_user_id"), table_name="sports_tracked_teams")
        op.drop_table("sports_tracked_teams")
