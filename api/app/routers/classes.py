from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, require_supabase_roles
from app.models.class_assignment import ClassTeacherAssignment
from app.models.student import Student
from app.models.user import User
from app.services.audit import write_audit

router = APIRouter(prefix="/classes", tags=["classes"])
SCHOOL_ROLES = ("owner", "headmaster", "teacher")


def _school(principal: SupabasePrincipal, requested: Optional[int]) -> int:
    if principal.is_admin or principal.role not in SCHOOL_ROLES or principal.school_id is None:
        raise HTTPException(status_code=403, detail="School class access required")
    if requested is not None and requested != principal.school_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal.school_id


class AssignmentCreate(BaseModel):
    class_name: str = Field(min_length=1, max_length=40)
    teacher_user_id: int

    @field_validator("class_name")
    @classmethod
    def normalize_class_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Class name is required")
        return value


@router.get("")
def list_classes(
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, school_id)
    query = db.query(
        Student.form.label("class_name"),
        func.count(Student.id).label("student_count"),
    ).filter(
        Student.school_id == sid,
        Student.form.isnot(None),
        Student.form != "",
    ).group_by(Student.form)
    classes = query.order_by(Student.form).all()
    assigned = None
    if principal.role == "teacher":
        assigned = {
            row[0] for row in db.query(ClassTeacherAssignment.class_name).filter(
                ClassTeacherAssignment.school_id == sid,
                ClassTeacherAssignment.teacher_user_id == principal.user_id,
                ClassTeacherAssignment.is_active.is_(True),
            ).all()
        }
    return [{
        "class_name": row.class_name,
        "student_count": int(row.student_count),
        "assigned_to_me": assigned is not None and row.class_name in assigned,
    } for row in classes if assigned is None or row.class_name in assigned]


@router.get("/assignments")
def list_assignments(
    school_id: Optional[int] = Query(None),
    principal: SupabasePrincipal = Depends(require_supabase_roles(*SCHOOL_ROLES)),
    db: Session = Depends(get_db),
):
    sid = _school(principal, school_id)
    query = (
        db.query(ClassTeacherAssignment, User)
        .join(User, User.id == ClassTeacherAssignment.teacher_user_id)
        .filter(
            ClassTeacherAssignment.school_id == sid,
            ClassTeacherAssignment.is_active.is_(True),
        )
    )
    if principal.role == "teacher":
        query = query.filter(ClassTeacherAssignment.teacher_user_id == principal.user_id)
    rows = query.order_by(ClassTeacherAssignment.class_name, User.full_name).all()
    return [{
        "id": assignment.id, "class_name": assignment.class_name,
        "teacher_user_id": teacher.id, "teacher_name": teacher.full_name,
        "teacher_email": teacher.email,
    } for assignment, teacher in rows]


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
def assign_class_teacher(
    payload: AssignmentCreate,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster")),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    if db.query(Student.id).filter(
        Student.school_id == sid, Student.form == payload.class_name, Student.status == "active"
    ).first() is None:
        raise HTTPException(status_code=404, detail="No active learners are registered in this class")
    teacher = db.query(User).filter(
        User.id == payload.teacher_user_id, User.school_id == sid,
        User.role == "teacher", User.is_active.is_(True), User.is_admin.is_(False),
    ).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Active teacher not found in this school")
    assignment = db.query(ClassTeacherAssignment).filter(
        ClassTeacherAssignment.school_id == sid,
        ClassTeacherAssignment.class_name == payload.class_name,
        ClassTeacherAssignment.teacher_user_id == teacher.id,
    ).with_for_update().first()
    if assignment and assignment.is_active:
        raise HTTPException(status_code=409, detail="This teacher is already assigned to the class")
    if assignment:
        assignment.is_active = True
        assignment.assigned_by_user_id = principal.user_id
    else:
        assignment = ClassTeacherAssignment(
            school_id=sid, class_name=payload.class_name,
            teacher_user_id=teacher.id, assigned_by_user_id=principal.user_id,
            is_active=True,
        )
        db.add(assignment)
    db.commit()
    db.refresh(assignment)
    write_audit(db, principal, "class.teacher.assign", "class_teacher_assignment", assignment.id, {
        "class_name": payload.class_name, "teacher_user_id": teacher.id,
    }, school_id=sid)
    return {"id": assignment.id, "class_name": assignment.class_name, "teacher_user_id": teacher.id}


@router.delete("/assignments/{assignment_id}")
def remove_class_teacher(
    assignment_id: int,
    principal: SupabasePrincipal = Depends(require_supabase_roles("owner", "headmaster")),
    db: Session = Depends(get_db),
):
    sid = _school(principal, None)
    assignment = db.query(ClassTeacherAssignment).filter(
        ClassTeacherAssignment.id == assignment_id,
        ClassTeacherAssignment.school_id == sid,
        ClassTeacherAssignment.is_active.is_(True),
    ).with_for_update().first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Active class assignment not found")
    assignment.is_active = False
    details = {"class_name": assignment.class_name, "teacher_user_id": assignment.teacher_user_id}
    db.commit()
    write_audit(db, principal, "class.teacher.unassign", "class_teacher_assignment", assignment.id, details, school_id=sid)
    return {"removed": True}
