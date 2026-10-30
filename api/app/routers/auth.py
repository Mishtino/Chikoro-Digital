from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal
from app.models.user import User
from app.models.student import Student
from app.schemas import auth as schemas
from app.services.auth import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    # allow students to log in with their student ID
    if user is None and "@" not in form.username:
        student = db.query(Student).filter(Student.student_number == form.username).first()
        if student and student.portal_user_id:
            user = db.get(User, student.portal_user_id)
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    # keep portal user name in sync with school records
    if user.role == "student":
        student = db.query(Student).filter(Student.portal_user_id == user.id).first()
        if student:
            user.full_name = f"{student.first_name} {student.last_name}"
            db.commit()
    token = create_access_token(str(user.id), user.school_id, user.role, user.is_admin)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    if user.role == "student":
        student = db.query(Student).filter(Student.portal_user_id == user.id).first()
        if student:
            user.full_name = f"{student.first_name} {student.last_name}"
            db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "school_id": user.school_id,
        "is_admin": user.is_admin,
    }
