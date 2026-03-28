from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.auth import DevLoginRequest
from app.schemas.user import UserCreate
from app.services.user_service import UserService


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_service = UserService(db)

    def dev_login(self, payload: DevLoginRequest):
        user = self.user_service.get_user_by_email(payload.email)
        if user is not None:
            if payload.full_name and user.full_name != payload.full_name:
                user.full_name = payload.full_name
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)
            return user

        return self.user_service.create_user(
            UserCreate(
                email=payload.email,
                full_name=payload.full_name,
                is_active=True,
            )
        )
