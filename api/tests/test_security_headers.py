from app.config import settings


def test_api_sets_baseline_security_headers(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["cache-control"] == "no-store"


def test_hsts_is_added_only_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    response = client.get("/health")
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_hsts_is_not_added_in_development(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "development")
    response = client.get("/health")
    assert "strict-transport-security" not in response.headers
