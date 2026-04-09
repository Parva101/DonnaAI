from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.token_crypto import encrypt_token
from app.models import ConnectedAccount, User
from app.schemas.connected_account import ConnectedAccountCreate, ConnectedAccountUpdate


class ConnectedAccountService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: UUID) -> list[ConnectedAccount]:
        stmt = (
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == user_id)
            .order_by(ConnectedAccount.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, account_id: UUID, *, user_id: UUID) -> ConnectedAccount | None:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.id == account_id,
            ConnectedAccount.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_provider(
        self, *, user_id: UUID, provider: str, provider_account_id: str
    ) -> ConnectedAccount | None:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.provider_account_id == provider_account_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, user: User, payload: ConnectedAccountCreate) -> ConnectedAccount:
        account = ConnectedAccount(
            user_id=user.id,
            provider=payload.provider,
            provider_account_id=payload.provider_account_id,
            account_email=payload.account_email,
            access_token_encrypted=encrypt_token(payload.access_token_encrypted),
            refresh_token_encrypted=encrypt_token(payload.refresh_token_encrypted),
            token_expires_at=payload.token_expires_at,
            scopes=payload.scopes,
            account_metadata=payload.account_metadata,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def update(
        self, account: ConnectedAccount, payload: ConnectedAccountUpdate
    ) -> ConnectedAccount:
        update_data = payload.model_dump(exclude_unset=True)
        if "access_token_encrypted" in update_data:
            update_data["access_token_encrypted"] = encrypt_token(update_data["access_token_encrypted"])
        if "refresh_token_encrypted" in update_data:
            update_data["refresh_token_encrypted"] = encrypt_token(update_data["refresh_token_encrypted"])
        for field, value in update_data.items():
            setattr(account, field, value)
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def delete(self, account: ConnectedAccount) -> None:
        self.db.delete(account)
        self.db.commit()
