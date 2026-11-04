from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.school import School
from app.services.audit import write_audit

router = APIRouter(prefix="/schools", tags=["schools"])


class SchoolCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=200)
    province: Optional[str] = Field(default=None, max_length=100)
    plan: Optional[str] = Field(default="pilot", max_length=50)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not all(ch.isalnum() or ch == "-" for ch in normalized):
            raise ValueError("School code may contain only letters, numbers and hyphens")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("School name cannot be empty")
        return normalized

    @field_validator("province", "plan")
    @classmethod
    def trim_optional_text(cls, value):
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None


class SchoolOut(BaseModel):
    id: int
    code: str
    name: str
    province: Optional[str] = None
    status: str
    plan: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
def create_school(payload: SchoolCreate, admin: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    if not admin.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    existing = db.query(School).filter(School.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="School code already exists")
    school = School(code=payload.code, name=payload.name, province=payload.province, plan=payload.plan)
    db.add(school)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="School code already exists")
    db.refresh(school)
    write_audit(db, admin, "school.create", "school", school.id, {"code": school.code}, school_id=None)
    return school


@router.get("", response_model=List[SchoolOut])
def list_schools(admin: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    if not admin.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")
    return db.query(School).order_by(School.id).all()


@router.get("/{school_id}", response_model=SchoolOut)
def get_school(school_id: int, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if not principal.is_platform_admin and principal.school_id != school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return school
