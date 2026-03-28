from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.schemas.user import UserRead


class DevLoginRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None


class SessionRead(BaseModel):
    user: UserRead
