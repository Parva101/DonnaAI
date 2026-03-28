from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    def list_users(self) -> list[User]:
        return list(self.db.execute(select(User).order_by(User.created_at.desc())).scalars())

    def get_user(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def create_user(self, payload: UserCreate) -> User:
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            is_active=payload.is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
