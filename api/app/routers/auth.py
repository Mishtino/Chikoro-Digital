from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.profile import Profile
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_410_GONE)
def legacy_login_disabled():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Password sign-in has moved to Supabase Auth. Sign in through the Chikoro portal.",
    )


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    profile = db.get(Profile, principal.auth_user_id)
    return {
        "id": user.id,
        "auth_user_id": principal.auth_user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": profile.role,
        "school_id": profile.school_id,
        "is_admin": principal.is_admin,
    }
