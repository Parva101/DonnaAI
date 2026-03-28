from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.connected_account import (
    ConnectedAccountCreate,
    ConnectedAccountRead,
    ConnectedAccountUpdate,
)
from app.services.connected_account_service import ConnectedAccountService


router = APIRouter(prefix="/connected-accounts", tags=["connected-accounts"])


@router.get("", response_model=list[ConnectedAccountRead])
def list_connected_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConnectedAccountRead]:
    """List all connected accounts for the current user."""
    return ConnectedAccountService(db).list_for_user(current_user.id)


@router.post("", response_model=ConnectedAccountRead, status_code=status.HTTP_201_CREATED)
def create_connected_account(
    payload: ConnectedAccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAccountRead:
    """Connect a new third-party account for the current user."""
    svc = ConnectedAccountService(db)

    existing = svc.get_by_provider(
        user_id=current_user.id,
        provider=payload.provider,
        provider_account_id=payload.provider_account_id,
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account already connected for provider '{payload.provider}'.",
        )

    return svc.create(current_user, payload)


@router.get("/{account_id}", response_model=ConnectedAccountRead)
def get_connected_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAccountRead:
    """Get a specific connected account (must belong to current user)."""
    account = ConnectedAccountService(db).get(account_id, user_id=current_user.id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected account not found.",
        )
    return account


@router.patch("/{account_id}", response_model=ConnectedAccountRead)
def update_connected_account(
    account_id: UUID,
    payload: ConnectedAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectedAccountRead:
    """Update a connected account (e.g. refresh tokens)."""
    svc = ConnectedAccountService(db)
    account = svc.get(account_id, user_id=current_user.id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected account not found.",
        )
    return svc.update(account, payload)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connected_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Disconnect (delete) a connected account."""
    svc = ConnectedAccountService(db)
    account = svc.get(account_id, user_id=current_user.id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected account not found.",
        )
    svc.delete(account)
