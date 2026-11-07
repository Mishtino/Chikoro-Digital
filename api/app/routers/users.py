from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])

SCHOOL_STAFF_ROLES = ("owner", "headmaster", "bursar", "teacher")


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: str = "staff"
    school_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    school_id: Optional[int] = None
    is_active: bool
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)


@router.post("", status_code=status.HTTP_410_GONE)
def create_user():
    """Local-password provisioning is disabled; accounts must be created in Supabase Auth."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Local-password user creation is disabled. Use the verified Supabase invitation workflow.",
    )


@router.get("", response_model=List[UserOut])
def list_users(
    school_id: Optional[int] = None,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    """List staff for exactly one school; never expose a cross-school user directory."""
    if principal.role in ("owner", "headmaster") and not principal.is_admin:
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="School-scoped administrator access required")
        if school_id is not None and school_id != principal.school_id:
            raise HTTPException(status_code=403, detail="Access denied")
        target_school_id = principal.school_id
    elif principal.is_platform_admin:
        if school_id is None:
            raise HTTPException(status_code=400, detail="school_id is required for the platform staff directory")
        target_school_id = school_id
    else:
        raise HTTPException(status_code=403, detail="School administrator access required")

    return (
        db.query(User)
        .filter(
            User.school_id == target_school_id,
            User.role.in_(SCHOOL_STAFF_ROLES),
        )
        .order_by(User.full_name, User.id)
        .all()
    )
