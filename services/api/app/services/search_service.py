from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.message import Message


def search_messages(
    db: Session,
    tenant_id: str,
    platform: str | None = None,
    chat_key: str | None = None,
    query: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 20,
) -> list[Message]:
    stmt: Select[tuple[Message]] = select(Message).where(Message.tenant_id == tenant_id)

    if platform:
        stmt = stmt.where(Message.platform == platform)
    if chat_key:
        stmt = stmt.where(Message.chat_key == chat_key)
    if since:
        stmt = stmt.where(Message.sent_at >= since)
    if until:
        stmt = stmt.where(Message.sent_at <= until)
    if query:
        stmt = stmt.where(Message.body_text.ilike(f"%{query}%"))

    stmt = stmt.order_by(Message.sent_at.desc()).limit(max(1, min(limit, 100)))
    return list(db.scalars(stmt).all())

