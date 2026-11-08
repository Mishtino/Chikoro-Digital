from fastapi import HTTPException

from app.models.class_assignment import ClassTeacherAssignment


def assigned_class_names(db, principal, school_id):
    if principal.role != "teacher" or principal.is_admin or principal.school_id != school_id:
        return None
    return {
        row[0] for row in db.query(ClassTeacherAssignment.class_name).filter(
            ClassTeacherAssignment.school_id == school_id,
            ClassTeacherAssignment.teacher_user_id == principal.user_id,
            ClassTeacherAssignment.is_active.is_(True),
        ).all()
    }


def require_teacher_class(db, principal, school_id, class_name):
    allowed = assigned_class_names(db, principal, school_id)
    if allowed is not None and class_name not in allowed:
        raise HTTPException(status_code=403, detail="You are not assigned to this class")
    return True
