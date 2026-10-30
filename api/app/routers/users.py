from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.user import User
from app.services.auth import hash_password
from app.services.audit import write_audit

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


def _can_manage(principal: Principal, school_id: Optional[int]) -> bool:
    if principal.is_admin:
        return True
    if school_id is not None and principal.school_id == school_id and principal.role in ("owner", "headmaster"):
        return True
    return False


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    school_id = payload.school_id
    if not principal.is_admin:
        # school users can only create users in their own school
        school_id = principal.school_id
    if not _can_manage(principal, school_id):
        raise HTTPException(status_code=403, detail="Not allowed")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        school_id=school_id,
        is_admin=(payload.role == "admin"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    write_audit(db, principal, "user.create", "user", user.id, {"email": user.email, "role": user.role}, school_id=school_id)
    return user


@router.get("", response_model=List[UserOut])
def list_users(school_id: Optional[int] = None, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    q = db.query(User)
    if principal.is_admin:
        if school_id is not None:
            q = q.filter(User.school_id == school_id)
    else:
        q = q.filter(User.school_id == principal.school_id)
    return q.order_by(User.id).all()
