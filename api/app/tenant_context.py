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

    def close(self):
        try:
            super().close()
        finally:
            self.info.pop("tenant_context", None)


@event.listens_for(TenantContextSession, "after_begin")
def _apply_context(session, transaction, connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Tenant context requires PostgreSQL")
    context = session.info.get("tenant_context")
    # Always overwrite every supported key, including for anonymous requests.
    # Empty values intentionally make policies using NULLIF(..., '') deny rows.
    values = {
        "request.jwt.claim.sub": str(context.auth_user_id) if context else "",
        "app.auth_user_id": str(context.auth_user_id) if context else "",
        "app.local_user_id": str(context.local_user_id) if context else "",
        "app.school_id": str(context.school_id) if context and context.school_id is not None else "",
        "app.role": context.role if context else "",
        "app.is_platform_admin": "false",
        "app.request_kind": "ordinary",
    }
    for key, value in values.items():
        connection.execute(text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value})
