from fastapi import APIRouter, Depends

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.services.platform_access import permissions_for

router = APIRouter(prefix="/platform/access", tags=["platform-access"])


@router.get("/me")
def get_platform_access(principal: SupabasePrincipal = Depends(get_supabase_principal)):
    """Return server-authorized platform role and permissions for the signed-in user."""
    return {
        "is_platform_staff": principal.is_platform_staff,
        "is_platform_admin": principal.is_platform_admin,
        "role": principal.role if principal.is_platform_staff else None,
        "permissions": permissions_for(principal),
    }
