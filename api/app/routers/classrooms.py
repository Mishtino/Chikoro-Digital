"""Classroom scheduling only. No join tokens or external URLs are exposed."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.classroom import ClassroomSession, ClassroomSettings
from app.services.classroom_access import require_classroom_host, require_classroom_student

router = APIRouter(prefix="/classrooms", tags=["classrooms"])


class ScheduleClassroom(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    mode: Literal["embedded", "external"]
    provider: Literal["jitsi", "google_meet", "zoom", "teams"]
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_schedule(self):
        self.class_name = self.class_name.strip()
        if not self.class_name:
            raise ValueError("Class name required")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Timezone-aware timestamps required")
        if self.starts_at >= self.ends_at:
            raise ValueError("End must follow start")
        if (self.ends_at - self.starts_at).total_seconds() > 4 * 3600:
            raise ValueError("Maximum session duration is four hours")
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError("Session must start in the future")
        if self.mode == "embedded" and self.provider != "jitsi":
            raise ValueError("Only the Jitsi embedded adapter is proposed")
        if self.mode == "external" and self.provider not in ("jitsi", "google_meet", "zoom", "teams"):
            raise ValueError("Unsupported external provider")
        return self


def school_id(principal):
    if principal.is_admin or principal.school_id is None:
        raise HTTPException(status_code=403, detail="Institution access required")
    return principal.school_id


@router.post("", status_code=status.HTTP_201_CREATED)
def schedule_classroom(
    payload: ScheduleClassroom,
    principal: SupabasePrincipal = Depends(require_supabase_roles("teacher")),
    db: Session = Depends(get_db),
):
    sid = school_id(principal)
    require_classroom_host(db, principal, sid, payload.class_name)
    settings = db.query(ClassroomSettings).filter(ClassroomSettings.school_id == sid).first()
    if settings is None or not (
        settings.embedded_enabled if payload.mode == "embedded" else settings.external_enabled
    ):
        raise HTTPException(status_code=403, detail="Classroom mode is not enabled")
    session = ClassroomSession(
        school_id=sid, class_name=payload.class_name, host_user_id=principal.user_id,
        created_by_user_id=principal.user_id, mode=payload.mode,
        provider=payload.provider, starts_at=payload.starts_at,
        ends_at=payload.ends_at, status="scheduled",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "status": session.status}


@router.get("")
def list_classrooms(
    principal: SupabasePrincipal = Depends(require_supabase_roles("teacher", "student")),
    db: Session = Depends(get_db),
):
    sid = school_id(principal)
    rows = db.query(ClassroomSession).filter(
        ClassroomSession.school_id == sid,
        ClassroomSession.status.in_(("scheduled", "live")),
    ).order_by(ClassroomSession.starts_at).limit(100).all()
    visible = []
    for row in rows:
        try:
            if principal.role == "teacher":
                require_classroom_host(db, principal, sid, row.class_name)
            else:
                require_classroom_student(db, principal, sid, row.class_name)
        except HTTPException:
            continue
        visible.append({
            "id": row.id, "class_name": row.class_name,
            "mode": row.mode, "provider": row.provider,
            "starts_at": row.starts_at, "ends_at": row.ends_at,
            "status": row.status,
        })
    return visible
