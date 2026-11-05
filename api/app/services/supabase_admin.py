"""Trusted-server Supabase Auth Admin operations for platform staff.

Admin credentials are sent only to the configured Supabase Auth origin. Redirects
are deliberately disabled so a credential-bearing request cannot be forwarded
to another host.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from app.config import settings


class SupabaseAdminError(Exception):
    def __init__(self, status_code=None):
        self.status_code = status_code
        super().__init__("Supabase Auth Admin request failed")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _auth_origin() -> str:
    """Validate the configured Auth origin before attaching the admin secret."""
    raw = (settings.supabase_url or "").strip()
    if not raw:
        raise RuntimeError("Supabase Auth Admin is not configured")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        raise RuntimeError("Supabase Auth Admin is not configured") from None

    local_http = (
        settings.env != "production"
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and port in {None, 54321}
    )
    secure_https = (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and port in {None, 443}
    )
    if (
        not (local_http or secure_https)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Supabase Auth Admin is not configured")
    return f"{parsed.scheme}://{parsed.netloc}"


def _admin_request(path: str, method: str, payload=None):
    base = _auth_origin()
    secret = (settings.supabase_secret_key or "").strip()
    if not secret:
        raise RuntimeError("Supabase Auth Admin is not configured")
    if path != "/invite" and not re.fullmatch(
        r"/admin/users/[0-9a-fA-F-]{36}", path
    ):
        raise ValueError("Unsupported Supabase Auth Admin operation")

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
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=8) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(result, dict):
                raise ValueError("Unexpected Supabase Auth Admin response")
            return result
    except HTTPError as exc:
        # Do not follow redirects and never expose upstream response bodies.
        raise SupabaseAdminError(exc.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SupabaseAdminError() from None


def invite_auth_user(email: str, full_name: str) -> str:
    result = _admin_request(
        "/invite",
        "POST",
        {"email": email, "data": {"full_name": full_name}},
    )
    try:
        auth_user_id = str(UUID(str(result.get("id"))))
    except (ValueError, TypeError, AttributeError):
        raise SupabaseAdminError() from None
    returned_email = (result.get("email") or "").strip().lower()
    if returned_email != email.strip().lower():
        raise SupabaseAdminError()
    return auth_user_id


def delete_auth_user(auth_user_id: str) -> None:
    try:
        normalized_id = str(UUID(str(auth_user_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid Supabase Auth user ID") from None
    _admin_request(f"/admin/users/{normalized_id}", "DELETE")
