"""AI productivity API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.ai import (
    ActionItemExtractRequest,
    ActionItemExtractResponse,
    ActionItemListResponse,
    ActionItemRead,
    ActionItemUpdate,
    PriorityScoreRequest,
    PriorityScoreResponse,
    PriorityScoreResult,
    ReplySuggestionsRequest,
    ReplySuggestionsResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchItem,
)
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/reply-suggestions", response_model=ReplySuggestionsResponse)
async def get_reply_suggestions(
    payload: ReplySuggestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReplySuggestionsResponse:
    del current_user
    svc = AIService(db)
    suggestions = await svc.generate_reply_suggestions(
        context=payload.context,
        tone=payload.tone,
        platform=payload.platform,
    )
    return ReplySuggestionsResponse(suggestions=suggestions)


@router.post("/priority/score", response_model=PriorityScoreResponse)
def score_priority(
    payload: PriorityScoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PriorityScoreResponse:
    if not payload.email_ids:
        return PriorityScoreResponse(results=[])

    svc = AIService(db)
    scored = svc.score_emails(user_id=current_user.id, email_ids=payload.email_ids)
    return PriorityScoreResponse(
        results=[
            PriorityScoreResult(email_id=email_id, score=score, label=label)
            for email_id, score, label in scored
        ]
    )


def _to_action_item(item) -> ActionItemRead:
    return ActionItemRead(
        id=item.id,
        user_id=item.user_id,
        source_platform=item.source_platform,
        source_ref=item.source_ref,
        title=item.title,
        details=item.details,
        status=item.status,
        priority=item.priority,
        score=item.score,
        due_at=item.due_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/action-items/extract", response_model=ActionItemExtractResponse)
def extract_action_items(
    payload: ActionItemExtractRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemExtractResponse:
    svc = AIService(db)
    created = svc.extract_action_items(
        user_id=current_user.id,
        source_platform=payload.source_platform,
        source_ref=payload.source_ref,
        text=payload.text,
    )
    return ActionItemExtractResponse(items=[_to_action_item(item) for item in created])


@router.get("/action-items", response_model=ActionItemListResponse)
def list_action_items(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemListResponse:
    svc = AIService(db)
    items = svc.list_action_items(user_id=current_user.id, status=status_filter)
    return ActionItemListResponse(items=[_to_action_item(item) for item in items], total=len(items))


@router.patch("/action-items/{action_item_id}", response_model=ActionItemRead)
def update_action_item(
    action_item_id: UUID,
    payload: ActionItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionItemRead:
    svc = AIService(db)
    item = svc.update_action_item(
        user_id=current_user.id,
        action_item_id=action_item_id,
        status=payload.status,
        priority=payload.priority,
        due_at=payload.due_at,
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")
    return _to_action_item(item)


@router.post("/search", response_model=SemanticSearchResponse)
def semantic_search(
    payload: SemanticSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SemanticSearchResponse:
    svc = AIService(db)
    matches = svc.semantic_search(
        user_id=current_user.id,
        query=payload.query,
        limit=payload.limit,
    )
    return SemanticSearchResponse(
        results=[
            SemanticSearchItem(
                email_id=email.id,
                score=score,
                subject=email.subject,
                from_address=email.from_address,
                snippet=email.snippet,
                category=email.category,
            )
            for email, score in matches
        ]
    )
