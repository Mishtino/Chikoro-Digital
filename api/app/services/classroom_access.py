"""Fail-closed classroom authorization helpers; not yet exposed as API routes.

All checks use resolved SupabasePrincipal and live tenant-scoped database rows.
A provider meeting URL or JWT user_metadata is never proof of enrolment.
"""
from fastapi import HTTPException

from app.models.class_assignment import ClassTeacherAssignment
from app.models.student import Student
from app.models.user import User


def require_classroom_host(db, principal, school_id: int, class_name: str) -> None:
    if (
        principal.is_admin or principal.role != "teacher"
        or principal.school_id is None or principal.school_id != school_id
        or not class_name or not class_name.strip()
    ):
        raise HTTPException(status_code=403, detail="Classroom host access denied")
    active_host = db.query(User.id).filter(
        User.id == principal.user_id, User.school_id == school_id,
        User.role == "teacher", User.is_active.is_(True),
        User.is_admin.is_(False),
    ).first()
    if active_host is None:
        raise HTTPException(status_code=403, detail="Inactive classroom host")
    assigned = db.query(ClassTeacherAssignment.id).filter(
        ClassTeacherAssignment.school_id == school_id,
        ClassTeacherAssignment.teacher_user_id == principal.user_id,
        ClassTeacherAssignment.class_name == class_name.strip(),
        ClassTeacherAssignment.is_active.is_(True),
    ).first()
    if assigned is None:
        raise HTTPException(status_code=403, detail="Class assignment required")


def require_classroom_student(db, principal, school_id: int, class_name: str) -> int:
    if (
        principal.is_admin or principal.role != "student"
        or principal.school_id is None or principal.school_id != school_id
        or not class_name or not class_name.strip()
    ):
        raise HTTPException(status_code=403, detail="Classroom enrolment required")
    active_user = db.query(User.id).filter(
        User.id == principal.user_id, User.school_id == school_id,
        User.role == "student", User.is_active.is_(True),
        User.is_admin.is_(False),
    ).first()
    if active_user is None:
        raise HTTPException(status_code=403, detail="Inactive student")
    student = db.query(Student.id).filter(
        Student.school_id == school_id,
        Student.portal_user_id == principal.user_id,
        Student.form == class_name.strip(),
        Student.status == "active",
    ).first()
    if student is None:
        raise HTTPException(status_code=403, detail="Active class enrolment required")
    return student[0]
