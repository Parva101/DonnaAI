from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.schemas.actions import ActionExecuteRequest, ActionPlanRequest
from app.services.permission_service import get_permission_scope


class ActionPolicyError(Exception):
    pass


def plan_action(db: Session, payload: ActionPlanRequest, trace_id: str) -> ActionLog:
    planned_payload = {
        "intent": payload.intent,
        "draft_message": f"[Draft] {payload.intent}",
    }

    action = ActionLog(
        tenant_id=payload.tenant_id,
        action_type="cross_platform_send",
        status="planned",
        source_platform=payload.source_platform,
        source_chat_key=payload.source_chat_key,
        target_platform=payload.target_platform,
        target_chat_key=payload.target_chat_key,
        payload_json=planned_payload,
        reason="Phase 0 planned action",
        confidence=0.5,
        requires_approval=True,
        idempotency_key=f"plan-{uuid4()}",
        trace_id=trace_id,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def get_action(db: Session, tenant_id: str, action_id: str) -> ActionLog | None:
    stmt = select(ActionLog).where(ActionLog.tenant_id == tenant_id, ActionLog.id == action_id)
    return db.scalar(stmt)


def execute_action(db: Session, payload: ActionExecuteRequest, trace_id: str) -> ActionLog:
    action = get_action(db, payload.tenant_id, payload.action_id)
    if action is None:
        raise ActionPolicyError("Action not found")

    existing_by_idempotency = db.scalar(
        select(ActionLog).where(
            ActionLog.tenant_id == payload.tenant_id,
            ActionLog.idempotency_key == payload.idempotency_key,
            ActionLog.status == "executed",
        )
    )
    if existing_by_idempotency is not None:
        return existing_by_idempotency

    if action.requires_approval and not payload.approval_token:
        action.status = "blocked"
        action.error_text = "Approval token required for execution"
        action.trace_id = trace_id
        db.commit()
        db.refresh(action)
        raise ActionPolicyError(action.error_text)

    if action.target_platform and action.target_chat_key:
        target_scope = get_permission_scope(
            db,
            tenant_id=payload.tenant_id,
            platform=action.target_platform,
            account_id=action.payload_json.get("target_account_id", "default"),
            chat_key=action.target_chat_key,
        )
        if target_scope is None or not target_scope.write_allowed:
            action.status = "blocked"
            action.error_text = "Target write scope is disabled"
            action.trace_id = trace_id
            db.commit()
            db.refresh(action)
            raise ActionPolicyError(action.error_text)

    action.idempotency_key = payload.idempotency_key
    action.status = "executed"
    action.trace_id = trace_id
    action.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(action)
    return action

