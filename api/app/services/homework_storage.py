"""Private Supabase Storage operations for homework attachments.

Only the trusted API uses the Supabase secret key. Browser clients receive
short-lived, object-specific signed URLs after application authorization.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import settings


BUCKET = "homework-private"


class StorageOperationError(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _origin():
    raw = (settings.supabase_url or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        raise StorageOperationError() from None
    valid = (
        parsed.scheme == "https" and bool(parsed.hostname) and port in {None, 443}
        and parsed.username is None and parsed.password is None
        and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
    )
    local = (
        settings.env != "production" and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and port in {None, 54321} and parsed.path in {"", "/"}
        and parsed.username is None and parsed.password is None
        and not parsed.query and not parsed.fragment
    )
    if not (valid or local) or not settings.supabase_secret_key.strip():
        raise StorageOperationError()
    return f"{parsed.scheme}://{parsed.netloc}"


def _request(path, method, payload=None):
    origin = _origin()
    secret = settings.supabase_secret_key.strip()
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": secret,
        "Authorization": f"Bearer {secret}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{origin}/storage/v1{path}", data=body, method=method, headers=headers)
    try:
        with build_opener(_NoRedirect()).open(request, timeout=8) as response:
            raw = response.read()
            if method == "HEAD":
                return dict(response.headers.items())
            result = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(result, dict):
                raise StorageOperationError()
            return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise StorageOperationError() from None


def _signed_url(value):
    if not isinstance(value, str) or not value:
        raise StorageOperationError()
    origin = _origin()
    if value.startswith("/storage/v1/"):
        result = origin + value
    elif value.startswith("/"):
        result = origin + "/storage/v1" + value
    else:
        result = value
    parsed = urlsplit(result)
    expected = urlsplit(origin)
    if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
        raise StorageOperationError()
    return result


def create_upload_url(object_path: str) -> str:
    path = quote(object_path, safe="/")
    result = _request(f"/object/upload/sign/{BUCKET}/{path}", "POST", {"upsert": False})
    return _signed_url(result.get("url") or result.get("signedURL") or result.get("signedUrl"))


def create_download_url(object_path: str, expires_in: int = 300) -> str:
    path = quote(object_path, safe="/")
    result = _request(f"/object/sign/{BUCKET}/{path}", "POST", {"expiresIn": expires_in})
    return _signed_url(result.get("signedURL") or result.get("signedUrl") or result.get("url"))


def inspect_object(object_path: str):
    path = quote(object_path, safe="/")
    headers = _request(f"/object/{BUCKET}/{path}", "HEAD")
    try:
        size = int(headers.get("Content-Length") or headers.get("content-length") or 0)
    except (TypeError, ValueError):
        raise StorageOperationError() from None
    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    return {"size_bytes": size, "content_type": content_type.split(";")[0].strip().lower()}
