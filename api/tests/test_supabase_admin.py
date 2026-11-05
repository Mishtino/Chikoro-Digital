from urllib.error import HTTPError
from io import BytesIO
from uuid import uuid4

import pytest

from app.config import settings
from app.services import supabase_admin


@pytest.fixture
def configured_admin(monkeypatch):
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "supabase_url", "https://example-project.supabase.co")
    monkeypatch.setattr(settings, "supabase_secret_key", "server-only-secret")


@pytest.mark.parametrize("url", [
    "http://example-project.supabase.co",
    "https://user:pass@example-project.supabase.co",
    "https://example-project.supabase.co:8443",
    "https://example-project.supabase.co/other/path",
    "https://example-project.supabase.co/?redirect=https://evil.example",
    "https://example-project.supabase.co#fragment",
])
def test_auth_admin_rejects_unsafe_configured_origins(configured_admin, monkeypatch, url):
    monkeypatch.setattr(settings, "supabase_url", url)
    with pytest.raises(RuntimeError):
        supabase_admin._admin_request("/invite", "POST", {"email": "a@example.com"})


def test_production_rejects_local_http_auth_origin(configured_admin, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "supabase_url", "http://localhost:54321")
    with pytest.raises(RuntimeError):
        supabase_admin._admin_request("/invite", "POST", {"email": "a@example.com"})


def test_local_supabase_http_origin_allowed_outside_production(configured_admin, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "http://127.0.0.1:54321")
    assert supabase_admin._auth_origin() == "http://127.0.0.1:54321"


def test_admin_request_does_not_follow_redirects(configured_admin, monkeypatch):
    class RedirectingOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://example-project.supabase.co/auth/v1/invite"
            assert request.get_header("Authorization") == "Bearer server-only-secret"
            raise HTTPError(request.full_url, 302, "Found", {"Location": "https://evil.example"}, BytesIO())

    monkeypatch.setattr(supabase_admin, "build_opener", lambda handler: RedirectingOpener())
    with pytest.raises(supabase_admin.SupabaseAdminError) as error:
        supabase_admin._admin_request("/invite", "POST", {"email": "a@example.com"})
    assert error.value.status_code == 302


def test_invite_requires_valid_uuid_and_matching_email(configured_admin, monkeypatch):
    monkeypatch.setattr(supabase_admin, "_admin_request", lambda *args, **kwargs: {
        "id": "not-a-uuid", "email": "a@example.com"
    })
    with pytest.raises(supabase_admin.SupabaseAdminError):
        supabase_admin.invite_auth_user("a@example.com", "A User")

    monkeypatch.setattr(supabase_admin, "_admin_request", lambda *args, **kwargs: {
        "id": str(uuid4()), "email": "other@example.com"
    })
    with pytest.raises(supabase_admin.SupabaseAdminError):
        supabase_admin.invite_auth_user("a@example.com", "A User")


def test_delete_auth_user_rejects_invalid_identifier(configured_admin, monkeypatch):
    monkeypatch.setattr(supabase_admin, "_admin_request", lambda *args, **kwargs: pytest.fail("must not call upstream"))
    with pytest.raises(ValueError):
        supabase_admin.delete_auth_user("not-a-uuid")
