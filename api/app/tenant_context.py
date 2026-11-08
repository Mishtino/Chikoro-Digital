"""Opt-in staging foundation; not wired into the production Session factory.

Only trusted server code may bind context after identity/profile verification.
Custom PostgreSQL settings are not a defense against arbitrary SQL execution.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TenantContext:
    auth_user_id: UUID
    local_user_id: int
    school_id: int | None
    role: str

    def __post_init__(self):
        if not isinstance(self.auth_user_id, UUID):
            raise ValueError("Verified Auth UUID required")
        if type(self.local_user_id) is not int or self.local_user_id <= 0:
            raise ValueError("Positive local user ID required")
        if self.school_id is not None and (type(self.school_id) is not int or self.school_id <= 0):
            raise ValueError("School ID must be positive or None")
        if not isinstance(self.role, str) or not self.role.strip():
            raise ValueError("Trusted profile role required")


class TenantContextSession(Session):
    """Reapply context at each transaction; clear it when a Session is closed."""

    def bind_tenant_context(self, context: TenantContext):
        if self.in_transaction():
            raise RuntimeError("Bind verified context before starting a transaction")
        if not isinstance(context, TenantContext):
            raise TypeError("TenantContext required")
        self.info["tenant_context"] = context

    def begin_identity_resolution(self, verified_subject: UUID):
        """Bootstrap only from a cryptographically verified token subject."""
        if self.in_transaction() or self.info.get("tenant_context") or self.info.get("verified_subject"):
            raise RuntimeError("Identity resolution requires a fresh Session")
        if not isinstance(verified_subject, UUID):
            raise ValueError("Verified Auth UUID required")
        self.info["verified_subject"] = verified_subject

    def complete_identity_resolution(self, context: TenantContext):
        """Promote only a profile resolved for this Session's verified subject."""
        if not isinstance(context, TenantContext):
            raise TypeError("TenantContext required")
        if (not self.in_transaction() or self.info.get("tenant_context")
                or self.info.get("verified_subject") != context.auth_user_id):
            raise RuntimeError("Resolved context must match the bootstrapped identity")
        self.info["tenant_context"] = context
        _apply_context(self, None, self.connection())

    def reject_identity_resolution(self):
        try:
            self.rollback()
        finally:
            self.info.pop("tenant_context", None)
            self.info.pop("verified_subject", None)

    def close(self):
        try:
            super().close()
        finally:
            self.info.pop("tenant_context", None)
            self.info.pop("verified_subject", None)


@event.listens_for(TenantContextSession, "after_begin")
def _apply_context(session, transaction, connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Tenant context requires PostgreSQL")
    context = session.info.get("tenant_context")
    subject = context.auth_user_id if context else session.info.get("verified_subject")
    # Always overwrite every supported key, including for anonymous requests.
    # Empty values intentionally make policies using NULLIF(..., '') deny rows.
    values = {
        "request.jwt.claim.sub": str(subject) if subject else "",
        "app.auth_user_id": str(subject) if subject else "",
        "app.local_user_id": str(context.local_user_id) if context else "",
        "app.school_id": str(context.school_id) if context and context.school_id is not None else "",
        "app.role": context.role if context else "",
        "app.is_platform_admin": "false",
        "app.request_kind": "ordinary",
    }
    for key, value in values.items():
        connection.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})
