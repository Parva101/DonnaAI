from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission_scope import PermissionScope
from app.schemas.permissions import PermissionScopeUpsertRequest


def upsert_permission_scope(db: Session, payload: PermissionScopeUpsertRequest) -> PermissionScope:
    stmt = select(PermissionScope).where(
        PermissionScope.tenant_id == payload.tenant_id,
        PermissionScope.platform == payload.platform,
        PermissionScope.account_id == payload.account_id,
        PermissionScope.chat_key == payload.chat_key,
    )
    existing = db.scalar(stmt)
    if existing is None:
        existing = PermissionScope(
            tenant_id=payload.tenant_id,
            platform=payload.platform,
            account_id=payload.account_id,
            chat_key=payload.chat_key,
            read_allowed=payload.read_allowed,
            write_allowed=payload.write_allowed,
            relay_allowed=payload.relay_allowed,
            updated_by=payload.updated_by,
        )
        db.add(existing)
    else:
        existing.read_allowed = payload.read_allowed
        existing.write_allowed = payload.write_allowed
        existing.relay_allowed = payload.relay_allowed
        existing.updated_by = payload.updated_by

    db.commit()
    db.refresh(existing)
    return existing


def list_permission_scopes(db: Session, tenant_id: str, platform: str | None = None) -> list[PermissionScope]:
    stmt = select(PermissionScope).where(PermissionScope.tenant_id == tenant_id)
    if platform:
        stmt = stmt.where(PermissionScope.platform == platform)
    stmt = stmt.order_by(PermissionScope.platform.asc(), PermissionScope.chat_key.asc())
    return list(db.scalars(stmt).all())


def get_permission_scope(
    db: Session, tenant_id: str, platform: str, account_id: str, chat_key: str
) -> PermissionScope | None:
    stmt = select(PermissionScope).where(
        PermissionScope.tenant_id == tenant_id,
        PermissionScope.platform == platform,
        PermissionScope.account_id == account_id,
        PermissionScope.chat_key == chat_key,
    )
    return db.scalar(stmt)

