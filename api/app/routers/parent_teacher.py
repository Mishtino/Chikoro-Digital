from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.models.parent_teacher_message import ParentTeacherConversation, ParentTeacherMessage
from app.models.student import Student
from app.models.user import User
from app.services.audit import write_audit
from app.services.class_access import require_teacher_class
from app.routers.portal import _parent_student

router = APIRouter(prefix="/communications", tags=["parent-teacher-communications"])


class ConversationCreate(BaseModel):
    student_id: int
    teacher_user_id: int
    subject: str = Field(min_length=1, max_length=160)

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A subject is required")
        return value


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value


def _school_principal(principal: SupabasePrincipal):
    if principal.is_admin or principal.school_id is None or principal.role not in {"parent", "teacher"}:
        raise HTTPException(status_code=403, detail="Parent or teacher school account required")
    return principal.school_id


def _teacher_assignment(db: Session, principal: SupabasePrincipal, student: Student):
    if principal.role != "teacher" or principal.school_id != student.school_id:
        raise HTTPException(status_code=403, detail="Teacher access required")
    require_teacher_class(db, principal, student.school_id, student.form or "")
    return True


def _conversation_for_actor(db: Session, principal: SupabasePrincipal, conversation_id: int):
    school_id = _school_principal(principal)
    conversation = db.query(ParentTeacherConversation).filter(
        ParentTeacherConversation.id == conversation_id,
        ParentTeacherConversation.school_id == school_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if principal.role == "parent":
        if conversation.parent_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        student = _parent_student(principal, conversation.student_id, db)
    else:
        if conversation.teacher_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        student = db.query(Student).filter(
            Student.id == conversation.student_id,
            Student.school_id == school_id,
            Student.status == "active",
        ).first()
        if student is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        _teacher_assignment(db, principal, student)
    return conversation, student


def _conversation_json(db, conversation, student):
    parent = db.query(User).filter(
        User.id == conversation.parent_user_id,
        User.school_id == conversation.school_id,
    ).first()
    teacher = db.query(User).filter(
        User.id == conversation.teacher_user_id,
        User.school_id == conversation.school_id,
    ).first()
    last_message = db.query(ParentTeacherMessage).filter(
        ParentTeacherMessage.school_id == conversation.school_id,
        ParentTeacherMessage.conversation_id == conversation.id,
    ).order_by(ParentTeacherMessage.id.desc()).first()
    return {
        "id": conversation.id,
        "student_id": student.id,
        "student_name": f"{student.first_name} {student.last_name}",
        "student_number": student.student_number,
        "subject": conversation.subject,
        "status": conversation.status,
        "parent_user_id": conversation.parent_user_id,
        "parent_name": parent.full_name if parent else "Parent",
        "teacher_user_id": conversation.teacher_user_id,
        "teacher_name": teacher.full_name if teacher else "Teacher",
        "last_message": last_message.body[:180] if last_message else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
    }



@router.get("/teachers")
def available_teachers(
    student_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    _school_principal(principal)
    if principal.role != "parent":
        raise HTTPException(status_code=403, detail="Parent portal only")
    student = _parent_student(principal, student_id, db)
    if not student.form:
        return {"teachers": []}
    from app.models.class_assignment import ClassTeacherAssignment
    rows = db.query(User).join(
        ClassTeacherAssignment,
        (ClassTeacherAssignment.teacher_user_id == User.id)
        & (ClassTeacherAssignment.school_id == User.school_id),
    ).filter(
        User.school_id == student.school_id,
        User.role == "teacher",
        User.is_active.is_(True),
        User.is_admin.is_(False),
        ClassTeacherAssignment.school_id == student.school_id,
        ClassTeacherAssignment.class_name == student.form,
        ClassTeacherAssignment.is_active.is_(True),
    ).order_by(User.full_name).all()
    return {"teachers": [{"id": row.id, "name": row.full_name} for row in rows]}


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    school_id = _school_principal(principal)
    if principal.role != "parent":
        raise HTTPException(status_code=403, detail="Only a verified parent can start a conversation")

    student = _parent_student(principal, payload.student_id, db)
    if not student.form:
        raise HTTPException(status_code=409, detail="This learner has no class assignment on record")
    teacher = db.query(User).filter(
        User.id == payload.teacher_user_id,
        User.school_id == school_id,
        User.role == "teacher",
        User.is_active.is_(True),
        User.is_admin.is_(False),
    ).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Assigned teacher not found")

    from app.models.class_assignment import ClassTeacherAssignment
    assignment = db.query(ClassTeacherAssignment).filter(
        ClassTeacherAssignment.school_id == school_id,
        ClassTeacherAssignment.class_name == student.form,
        ClassTeacherAssignment.teacher_user_id == teacher.id,
        ClassTeacherAssignment.is_active.is_(True),
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Teacher is not assigned to this learner's class")

    conversation = db.query(ParentTeacherConversation).filter(
        ParentTeacherConversation.school_id == school_id,
        ParentTeacherConversation.student_id == student.id,
        ParentTeacherConversation.parent_user_id == principal.user_id,
        ParentTeacherConversation.teacher_user_id == teacher.id,
        ParentTeacherConversation.subject == payload.subject,
    ).first()
    if conversation is None:
        conversation = ParentTeacherConversation(
            school_id=school_id, student_id=student.id,
            parent_user_id=principal.user_id, teacher_user_id=teacher.id,
            subject=payload.subject, status="open",
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        write_audit(db, principal, "communication.conversation.create",
                    "parent_teacher_conversation", conversation.id,
                    {"student_id": student.id, "teacher_user_id": teacher.id},
                    school_id=school_id)
    return _conversation_json(db, conversation, student)


@router.get("/conversations")
def list_conversations(
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    school_id = _school_principal(principal)
    query = db.query(ParentTeacherConversation).filter(
        ParentTeacherConversation.school_id == school_id,
    )
    if principal.role == "parent":
        # Re-resolve verified links on every request; stale links do not retain access.
        from sqlalchemy import text
        linked_ids = [row[0] for row in db.execute(text("""
            SELECT DISTINCT c.student_id
            FROM public.guardian_links gl
            JOIN public.contacts c ON c.id = gl.contact_id AND c.school_id = gl.school_id
            JOIN public.students s ON s.id = c.student_id AND s.school_id = c.school_id
            WHERE gl.profile_id = :profile_id AND gl.school_id = :school_id
              AND gl.is_active = true AND gl.verified_at IS NOT NULL AND s.status = 'active'
        """), {"profile_id": str(principal.auth_user_id), "school_id": school_id}).all()]
        query = query.filter(
            ParentTeacherConversation.parent_user_id == principal.user_id,
            ParentTeacherConversation.student_id.in_(linked_ids) if linked_ids else ParentTeacherConversation.id == -1,
        )
    else:
        from app.models.class_assignment import ClassTeacherAssignment
        assigned = [row[0] for row in db.query(ClassTeacherAssignment.class_name).filter(
            ClassTeacherAssignment.school_id == school_id,
            ClassTeacherAssignment.teacher_user_id == principal.user_id,
            ClassTeacherAssignment.is_active.is_(True),
        ).all()]
        if not assigned:
            return {"conversations": []}
        student_ids = [row[0] for row in db.query(Student.id).filter(
            Student.school_id == school_id, Student.status == "active",
            Student.form.in_(assigned),
        ).all()]
        query = query.filter(
            ParentTeacherConversation.teacher_user_id == principal.user_id,
            ParentTeacherConversation.student_id.in_(student_ids) if student_ids else ParentTeacherConversation.id == -1,
        )
    rows = query.order_by(ParentTeacherConversation.updated_at.desc()).limit(100).all()
    result = []
    for conversation in rows:
        student = db.query(Student).filter(
            Student.id == conversation.student_id, Student.school_id == school_id,
            Student.status == "active",
        ).first()
        if student:
            result.append(_conversation_json(db, conversation, student))
    return {"conversations": result}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    before_id: Optional[int] = Query(None, gt=0),
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    conversation, _student = _conversation_for_actor(db, principal, conversation_id)
    query = db.query(ParentTeacherMessage).filter(
        ParentTeacherMessage.school_id == conversation.school_id,
        ParentTeacherMessage.conversation_id == conversation.id,
    )
    if before_id:
        query = query.filter(ParentTeacherMessage.id < before_id)
    rows = query.order_by(ParentTeacherMessage.id.desc()).limit(100).all()
    return {"messages": [{
        "id": row.id, "sender_user_id": row.sender_user_id,
        "body": row.body, "created_at": row.created_at.isoformat(),
        "is_mine": row.sender_user_id == principal.user_id,
    } for row in reversed(rows)]}


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    conversation, _student = _conversation_for_actor(db, principal, conversation_id)
    if conversation.status != "open":
        raise HTTPException(status_code=409, detail="This conversation is closed")
    message = ParentTeacherMessage(
        school_id=conversation.school_id, conversation_id=conversation.id,
        sender_user_id=principal.user_id, body=payload.body,
    )
    db.add(message)
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    write_audit(db, principal, "communication.message.send",
                "parent_teacher_conversation", conversation.id,
                {"message_id": message.id, "body_length": len(payload.body)},
                school_id=conversation.school_id)
    return {
        "id": message.id, "sender_user_id": message.sender_user_id,
        "body": message.body, "created_at": message.created_at.isoformat(),
        "is_mine": True,
    }


@router.post("/conversations/{conversation_id}/close")
def close_conversation(
    conversation_id: int,
    principal: SupabasePrincipal = Depends(get_supabase_principal),
    db: Session = Depends(get_db),
):
    conversation, _student = _conversation_for_actor(db, principal, conversation_id)
    conversation.status = "closed"
    db.commit()
    write_audit(db, principal, "communication.conversation.close",
                "parent_teacher_conversation", conversation.id, {},
                school_id=conversation.school_id)
    return {"closed": True}
