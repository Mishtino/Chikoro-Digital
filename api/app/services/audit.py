from app.models.audit import AuditLog


def write_audit(db, principal_or_user_id, action, entity_type=None, entity_id=None, details=None, school_id=None):
    actor = None
    if hasattr(principal_or_user_id, "user_id"):
        actor = principal_or_user_id.user_id
        if school_id is None:
            school_id = principal_or_user_id.school_id
    else:
        actor = principal_or_user_id
    log = AuditLog(
        school_id=school_id,
        actor_user_id=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
    )
    db.add(log)
    db.commit()
    return log
