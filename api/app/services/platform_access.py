"""Central permission policy for Vortex platform-only roles.

Platform roles must be explicitly provisioned in trusted public.profiles and
must match a tenant-free local public.users record. Never trust user metadata.
"""
from fastapi import Depends, HTTPException

from app.deps_supabase import SupabasePrincipal, get_supabase_principal

ROLE_PERMISSIONS = {
    "vortex_admin": frozenset({
        "platform:access:read",
        "platform:staff:write",
        "schools:read",
        "schools:write",
        "schools:lifecycle",
        "audit:read",
    }),
    "vortex_support": frozenset({
        "platform:access:read",
        "schools:read",
    }),
    "vortex_auditor": frozenset({
        "platform:access:read",
        "audit:read",
    }),
    "vortex_billing": frozenset({
        "platform:access:read",
        "billing:read",
    }),
}


def permissions_for(principal: SupabasePrincipal) -> list[str]:
    if not principal.is_platform_staff:
        return []
    return sorted(ROLE_PERMISSIONS.get(principal.role, ()))


def require_platform_permission(permission: str):
    def dependency(principal: SupabasePrincipal = Depends(get_supabase_principal)):
        if permission not in permissions_for(principal):
            raise HTTPException(status_code=403, detail="Vortex platform permission required")
        return principal
    return dependency
