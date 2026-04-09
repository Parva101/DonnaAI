from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SportsTrackedTeam(TimestampMixin, Base):
    __tablename__ = "sports_tracked_teams"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "league",
            "team_id",
            name="uq_sports_tracked_teams_user_league_team",
        ),
        Index("ix_sports_tracked_teams_user_league", "user_id", "league"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    league: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_name: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
