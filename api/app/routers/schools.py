from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_principal, Principal, require_admin
from app.models.school import School
from app.services.audit import write_audit

router = APIRouter(prefix="/schools", tags=["schools"])


class SchoolCreate(BaseModel):
    code: str
    name: str
    province: Optional[str] = None
    plan: Optional[str] = "pilot"


class SchoolOut(BaseModel):
    id: int
    code: str
    name: str
    province: Optional[str] = None
    status: str
    plan: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
def create_school(payload: SchoolCreate, admin: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(School).filter(School.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="School code already exists")
    school = School(code=payload.code, name=payload.name, province=payload.province, plan=payload.plan)
    db.add(school)
    db.commit()
    db.refresh(school)
    write_audit(db, admin, "school.create", "school", school.id, {"code": school.code}, school_id=None)
    return school


@router.get("", response_model=List[SchoolOut])
def list_schools(admin: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(School).order_by(School.id).all()


@router.get("/{school_id}", response_model=SchoolOut)
def get_school(school_id: int, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    if not principal.is_admin and principal.school_id != school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return school
