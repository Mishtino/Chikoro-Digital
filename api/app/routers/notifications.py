from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.notification import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _sid(principal: Principal, requested: Optional[int]) -> int:
    if principal.is_admin:
        if requested is None:
            raise HTTPException(status_code=400, detail="school_id required")
        return requested
    if principal.school_id is None:
        raise HTTPException(status_code=403, detail="School context required")
    return principal.school_id


@router.get("")
def list_notifications(school_id: Optional[int] = Query(None), status_filter: Optional[str] = Query(None), principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    sid = _sid(principal, school_id) if (principal.is_admin or school_id is not None) else principal.school_id
    if sid is None:
        raise HTTPException(status_code=403, detail="School context required")
    q = db.query(Notification).filter(Notification.school_id == sid)
    if status_filter:
        q = q.filter(Notification.status == status_filter)
    return q.order_by(Notification.id.desc()).all()


@router.post("/process")
def process_notifications(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    if not principal.is_admin and principal.role not in ("owner", "headmaster"):
        raise HTTPException(status_code=403, detail="Not allowed")
    queued = db.query(Notification).filter(Notification.status == "queued").all()
    sent = 0
    for n in queued:
        # placeholder: actual delivery by channel would happen here
        n.status = "sent"
        n.sent_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
        n.attempts += 1
        sent += 1
    db.commit()
    return {"processed": sent}
