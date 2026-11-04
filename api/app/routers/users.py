from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


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

    class Config:
        from_attributes = True


def _can_manage(principal: SupabasePrincipal, school_id: Optional[int]) -> bool:
    if principal.is_admin:
        return True
    if school_id is not None and principal.school_id == school_id and principal.role in ("owner", "headmaster"):
        return True
    return False


@router.post("", status_code=status.HTTP_410_GONE)
def create_user():
    """Local-password provisioning is disabled; accounts must be created in Supabase Auth."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Local-password user creation is disabled. Use the verified Supabase invitation workflow.",
    )


@router.get("", response_model=List[UserOut])
def list_users(school_id: Optional[int] = None, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    q = db.query(User)
    if principal.is_admin:
        if school_id is not None:
            q = q.filter(User.school_id == school_id)
    else:
        q = q.filter(User.school_id == principal.school_id)
    return q.order_by(User.id).all()
