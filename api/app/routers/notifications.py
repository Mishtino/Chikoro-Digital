from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _sid(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.get("")
def list_notifications(school_id: Optional[int] = Query(None), status_filter: Optional[str] = Query(None), principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Notification).filter(Notification.school_id == sid)
    if status_filter:
        q = q.filter(Notification.status == status_filter)
    return q.order_by(Notification.id.desc()).all()


@router.post("/process")
def process_notifications(principal: SupabasePrincipal = Depends(require_supabase_roles('owner', 'headmaster')), db: Session = Depends(get_db)):
    if not principal.is_admin and principal.role not in ("owner", "headmaster"):
        raise HTTPException(status_code=403, detail="Not allowed")
    # Do not mark queued records as sent until a real email/SMS/push provider
    # is configured and delivery outcomes can be recorded truthfully.
    raise HTTPException(
        status_code=501,
        detail="Notification delivery is not configured. Queued notifications were not marked as sent.",
    )
