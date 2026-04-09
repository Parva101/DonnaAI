"""Voice call orchestration service.

Current implementation stores call intents and simulates completion so the UI and
API are end-to-end functional even without LiveKit/Twilio credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import VoiceCall


class VoiceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_calls(self, *, user_id: UUID, limit: int = 50) -> list[VoiceCall]:
        stmt = (
            select(VoiceCall)
            .where(VoiceCall.user_id == user_id)
            .order_by(VoiceCall.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def get_call(self, *, user_id: UUID, call_id: UUID) -> VoiceCall | None:
        call = self.db.get(VoiceCall, call_id)
        if not call or call.user_id != user_id:
            return None
        return call

    def create_call(
        self,
        *,
        user_id: UUID,
        intent: str,
        target_name: str | None,
        target_phone: str | None,
    ) -> VoiceCall:
        call = VoiceCall(
            user_id=user_id,
            target_name=target_name,
            target_phone=target_phone,
            intent=intent,
            status="queued",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)

        # Simulated completion path for local development.
        has_voice_stack = bool(
            settings.livekit_url
            and settings.livekit_api_key
            and settings.livekit_api_secret
            and settings.twilio_account_sid
            and settings.twilio_auth_token
        )

        if has_voice_stack:
            call.status = "queued_external"
            call.outcome = "Call queued for external LiveKit/Twilio pipeline."
            self.db.add(call)
            self.db.commit()
            self.db.refresh(call)
            return call

        call.status = "completed"
        call.transcript = (
            "Donna initiated the call flow in simulation mode. "
            "No external PSTN call was placed because voice provider credentials are not configured."
        )
        call.summary = "Simulation completed. Configure LiveKit and Twilio env vars for real calls."
        call.outcome = "No real call placed (simulation mode)."
        call.completed_at = datetime.now(timezone.utc)
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)
        return call
