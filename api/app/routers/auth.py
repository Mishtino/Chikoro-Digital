from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.profile import Profile
from app.models.student import Student
from app.models.user import User
from app.services.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def legacy_login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Preserve local development and test fixtures; production must use Supabase Auth.
    if settings.env == "production":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Password sign-in has moved to Supabase Auth. Sign in through the Chikoro portal.",
        )
    user = db.query(User).filter(User.email == form.username).first()
    if user is None and "@" not in form.username:
        student = db.query(Student).filter(Student.student_number == form.username).first()
        if student and student.portal_user_id:
            user = db.get(User, student.portal_user_id)
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": create_access_token(str(user.id), user.school_id, user.role, user.is_admin), "token_type": "bearer"}


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    profile = db.get(Profile, principal.auth_user_id) if principal.auth_user_id else None
    return {
        "id": user.id,
        "auth_user_id": principal.auth_user_id or None,
        "email": user.email,
        "full_name": user.full_name,
        "role": profile.role if profile else principal.role,
        "school_id": profile.school_id if profile else principal.school_id,
        "is_admin": principal.is_admin,
    }
