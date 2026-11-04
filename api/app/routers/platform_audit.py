from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.models.audit import AuditLog
from app.models.school import School
from app.models.user import User

router = APIRouter(prefix="/platform/audit-logs", tags=["platform-audit"])


class AuditLogOut(BaseModel):
    id: int
    school_id: Optional[int] = None
    school_name: Optional[str] = None
    actor_user_id: Optional[int] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    created_at: Any

    model_config = ConfigDict(from_attributes=True)


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    limit: int
    offset: int
    total: int


@router.get("", response_model=AuditLogPage)
def list_platform_audit_logs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    action: Optional[str] = Query(default=None, min_length=1, max_length=100),
    school_id: Optional[int] = Query(default=None, ge=1),
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")

    query = (
        db.query(AuditLog, User.full_name, User.email, School.name)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
        .outerjoin(School, AuditLog.school_id == School.id)
    )
    if action:
        query = query.filter(AuditLog.action == action.strip())
    if school_id is not None:
        query = query.filter(AuditLog.school_id == school_id)

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    items = [
        AuditLogOut(
            id=log.id,
            school_id=log.school_id,
            school_name=school_name,
            actor_user_id=log.actor_user_id,
            actor_name=actor_name,
            actor_email=actor_email,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            details=log.details,
            created_at=log.created_at,
        )
        for log, actor_name, actor_email, school_name in rows
    ]
    return AuditLogPage(items=items, limit=limit, offset=offset, total=total)
