from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class Principal:
    user_id: int
    school_id: Optional[int]
    role: str
    is_admin: bool


def get_current_principal(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Principal:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    return Principal(
        user_id=user.id,
        school_id=user.school_id,
        role=user.role,
        is_admin=user.is_admin,
    )


def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return principal


def require_school(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.school_id is None and not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="School context required")
    return principal
