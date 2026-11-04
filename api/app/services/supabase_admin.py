"""Trusted-server Supabase Auth Admin operations for platform staff."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


class SupabaseAdminError(Exception):
    def __init__(self, status_code=None):
        self.status_code = status_code
        super().__init__("Supabase Auth Admin request failed")


def _admin_request(path: str, method: str, payload=None):
    base = (settings.supabase_url or "").rstrip("/")
    secret = (settings.supabase_secret_key or "").strip()
    if not base or not secret:
        raise RuntimeError("Supabase Auth Admin is not configured")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base}/auth/v1{path}",
        data=body,
        method=method,
        headers={
            "apikey": secret,
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        raise SupabaseAdminError(exc.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SupabaseAdminError() from None


def invite_auth_user(email: str, full_name: str) -> str:
    result = _admin_request(
        "/invite",
        "POST",
        {"email": email, "data": {"full_name": full_name}},
    )
    auth_user_id = result.get("id")
    returned_email = (result.get("email") or "").strip().lower()
    if not auth_user_id or returned_email != email.lower():
        raise SupabaseAdminError()
    return str(auth_user_id)


def delete_auth_user(auth_user_id: str) -> None:
    _admin_request(f"/admin/users/{auth_user_id}", "DELETE")
