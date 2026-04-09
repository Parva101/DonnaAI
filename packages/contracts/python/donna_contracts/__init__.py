"""Shared contract package for DonnaAI services."""

from dataclasses import dataclass


@dataclass(slots=True)
class ActionContract:
    action_id: str
    action_type: str
    target_platform: str
    target_chat_key: str
    requires_approval: bool
    idempotency_key: str
    trace_id: str | None = None

