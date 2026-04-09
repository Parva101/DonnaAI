from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.actions import (
    ActionExecuteRequest,
    ActionExecuteResponse,
    ActionLogResponse,
    ActionPlanRequest,
    ActionPlanResponse,
)
from app.schemas.common import HealthResponse
from app.schemas.ingest import IngestEventRequest, IngestEventResponse
from app.schemas.permissions import PermissionScopeResponse, PermissionScopeUpsertRequest
from app.schemas.search import MessageSearchResult
from app.services.action_service import ActionPolicyError, execute_action, get_action, plan_action
from app.services.ingest_service import IngestPolicyError, ingest_event
from app.services.permission_service import list_permission_scopes, upsert_permission_scope
from app.services.search_service import search_messages

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="donnaai-api",
        timestamp=datetime.now(timezone.utc),
        version="phase0",
    )


@router.post("/v1/ingest/events", response_model=IngestEventResponse)
def create_ingest_event(
    payload: IngestEventRequest, db: Session = Depends(get_db)
) -> IngestEventResponse:
    try:
        event, created, message = ingest_event(db, payload)
        return IngestEventResponse(event_id=event.id, created=created, message_id=message.id if message else None)
    except IngestPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.put("/v1/permissions/scopes", response_model=PermissionScopeResponse)
def put_permission_scope(
    payload: PermissionScopeUpsertRequest, db: Session = Depends(get_db)
) -> PermissionScopeResponse:
    scope = upsert_permission_scope(db, payload)
    return PermissionScopeResponse.model_validate(scope)


@router.get("/v1/permissions/scopes", response_model=list[PermissionScopeResponse])
def get_permission_scopes(
    tenant_id: str = Query(...),
    platform: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PermissionScopeResponse]:
    rows = list_permission_scopes(db, tenant_id=tenant_id, platform=platform)
    return [PermissionScopeResponse.model_validate(row) for row in rows]


@router.get("/v1/search/messages", response_model=list[MessageSearchResult])
def get_messages(
    tenant_id: str = Query(...),
    platform: str | None = Query(default=None),
    chat_key: str | None = Query(default=None),
    q: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[MessageSearchResult]:
    rows = search_messages(
        db=db,
        tenant_id=tenant_id,
        platform=platform,
        chat_key=chat_key,
        query=q,
        since=since,
        until=until,
        limit=limit,
    )
    return [MessageSearchResult.model_validate(row) for row in rows]


@router.post("/v1/actions/plan", response_model=ActionPlanResponse)
def post_action_plan(
    payload: ActionPlanRequest, request: Request, db: Session = Depends(get_db)
) -> ActionPlanResponse:
    trace_id = getattr(request.state, "trace_id", None)
    action = plan_action(db, payload, trace_id=trace_id)
    return ActionPlanResponse(
        action_id=action.id,
        status=action.status,
        requires_approval=action.requires_approval,
        draft_payload=action.payload_json,
    )


@router.post("/v1/actions/execute", response_model=ActionExecuteResponse)
def post_action_execute(
    payload: ActionExecuteRequest, request: Request, db: Session = Depends(get_db)
) -> ActionExecuteResponse:
    trace_id = getattr(request.state, "trace_id", None)
    try:
        action = execute_action(db, payload, trace_id=trace_id)
    except ActionPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ActionExecuteResponse(
        action_id=action.id,
        status=action.status,
        executed_at=action.updated_at,
        message="Action executed (Phase 0 placeholder executor)",
    )


@router.get("/v1/actions/{action_id}", response_model=ActionLogResponse)
def get_action_state(
    action_id: str, tenant_id: str = Query(...), db: Session = Depends(get_db)
) -> ActionLogResponse:
    action = get_action(db, tenant_id=tenant_id, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return ActionLogResponse.model_validate(action)

