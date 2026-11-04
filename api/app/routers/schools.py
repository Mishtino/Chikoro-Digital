from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.deps_supabase import get_supabase_principal, SupabasePrincipal
from app.models.school import School
from app.services.audit import write_audit
from app.services.platform_access import require_platform_permission, permissions_for

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


class SchoolProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    province: Optional[str] = Field(default=None, max_length=100)
    plan: Optional[str] = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value):
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("School name cannot be empty")
        return normalized

    @field_validator("province", "plan")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one school profile field must be supplied")
        return self


class SchoolStatusUpdate(BaseModel):
    status: Literal["onboarding", "live", "suspended"]
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value):
        if value is None:
            return None
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
def list_schools(admin: SupabasePrincipal = Depends(require_platform_permission("schools:read")), db: Session = Depends(get_db)):
    return db.query(School).order_by(School.id).all()


@router.get("/{school_id}", response_model=SchoolOut)
def get_school(school_id: int, principal: SupabasePrincipal = Depends(get_supabase_principal), db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if principal.is_platform_staff:
        if "schools:read" not in permissions_for(principal):
            raise HTTPException(status_code=403, detail="Vortex platform permission required")
    elif principal.school_id != school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return school


@router.patch("/{school_id}", response_model=SchoolOut)
def update_school_profile(
    school_id: int,
    payload: SchoolProfileUpdate,
    admin: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if not admin.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")

    changes = {}
    for field, new_value in payload.model_dump(exclude_unset=True).items():
        old_value = getattr(school, field)
        if old_value != new_value:
            changes[field] = {"from": old_value, "to": new_value}
            setattr(school, field, new_value)

    if not changes:
        return school

    db.commit()
    db.refresh(school)
    write_audit(
        db,
        admin,
        "school.profile_update",
        "school",
        school.id,
        {"changes": changes},
        school_id=None,
    )
    return school


@router.patch("/{school_id}/status", response_model=SchoolOut)
def update_school_status(
    school_id: int,
    payload: SchoolStatusUpdate,
    admin: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    if not admin.is_platform_admin:
        raise HTTPException(status_code=403, detail="Vortex platform administrator access required")
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    previous_status = school.status
    if previous_status == payload.status:
        return school
    school.status = payload.status
    db.commit()
    db.refresh(school)
    write_audit(
        db,
        admin,
        "school.status_change",
        "school",
        school.id,
        {
            "previous_status": previous_status,
            "new_status": payload.status,
            "reason": payload.reason,
        },
        school_id=None,
    )
    return school
