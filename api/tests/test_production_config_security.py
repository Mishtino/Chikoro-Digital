
import pytest

from app.config import Settings, validate_production_settings


def safe_production_settings():
    return Settings(
        env="production",
        debug=False,
        database_url="postgresql+psycopg://app:strong-password@db.example.com:5432/chikoro",
        secret_key="a-unique-random-secret-with-more-than-32-characters",
        supabase_url="https://example-project.supabase.co",
        supabase_secret_key="test-service-secret",
        cors_origins="https://school.example.com,https://admin.example.com",
        homework_attachments_enabled=True,
    )


def test_accepts_explicit_hardened_production_configuration():
    validate_production_settings(safe_production_settings())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("secret_key", "change-me-in-production-please"),
        ("secret_key", "short"),
        ("debug", True),
        ("paynow_return_url", "http://school.example.com/paynow/return"),
        ("paynow_result_url", "http://api.example.com/paynow/webhook"),
        ("database_url", "sqlite:///./production.db"),
        ("supabase_url", "http://example-project.supabase.co"),
        ("supabase_url", "https://example-project.supabase.co/storage/v1"),
        ("supabase_url", "https://user:pass@example-project.supabase.co"),
        ("cors_origins", "*"),
        ("cors_origins", "http://school.example.com"),
        ("cors_origins", "https://user:pass@school.example.com"),
        ("cors_origins", "https://school.example.com/path"),
        ("supabase_secret_key", ""),
    ],
)
def test_rejects_unsafe_production_configuration(field, value):
    config = safe_production_settings()
    setattr(config, field, value)

    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_production_settings(config)


def test_development_configuration_is_not_blocked_by_production_guards():
    config = Settings(env="development", database_url="sqlite:///./dev.db")
    validate_production_settings(config)


def test_attachments_require_supabase_secret_key_only_when_enabled():
    config = safe_production_settings()
    config.homework_attachments_enabled = False
    config.supabase_secret_key = ""

    validate_production_settings(config)
