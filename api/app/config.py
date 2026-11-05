from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chikoro Digital API"
    env: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./chikoro.db"
    secret_key: str = "change-me-in-production-please"
    supabase_url: str = ""
    supabase_secret_key: str = ""
    school_staff_invitations_enabled: bool = False
    school_staff_lifecycle_enabled: bool = False
    homework_attachments_enabled: bool = False
    admin_bootstrap_token: str = ""
    platform_owner_email: str = ""
    access_token_expire_minutes: int = 60 * 8
    admin_mfa_required: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    paynow_return_url: str = "http://localhost:3000/paynow/return"
    paynow_result_url: str = "http://localhost:8000/paynow/webhook"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def validate_production_settings(config: Settings) -> None:
    """Fail closed when production is configured with unsafe application defaults."""
    if config.env.strip().lower() != "production":
        return

    from urllib.parse import urlsplit

    errors = []
    secret = (config.secret_key or "").strip()
    if secret in {"", "change-me-in-production-please"} or len(secret) < 32:
        errors.append("SECRET_KEY must be a unique random value of at least 32 characters")
    if config.debug:
        errors.append("DEBUG must be false in production")

    database = urlsplit((config.database_url or "").strip())
    if database.scheme not in {"postgres", "postgresql", "postgresql+psycopg"} or not database.hostname:
        errors.append("DATABASE_URL must point to PostgreSQL in production")

    supabase = urlsplit((config.supabase_url or "").strip())
    try:
        supabase.port
    except ValueError:
        errors.append("SUPABASE_URL must contain a valid port in production")
    if (
        supabase.scheme != "https"
        or not supabase.hostname
        or supabase.username
        or supabase.password
        or supabase.path not in {"", "/"}
        or supabase.query
        or supabase.fragment
    ):
        errors.append("SUPABASE_URL must be a clean HTTPS origin in production")

    origins = [origin.strip() for origin in (config.cors_origins or "").split(",") if origin.strip()]
    if not origins or "*" in origins:
        errors.append("CORS_ORIGINS must contain explicit HTTPS origins in production")
    else:
        for origin in origins:
            parsed = urlsplit(origin)
            try:
                parsed.port
                valid_origin = (
                    parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and not parsed.username
                    and not parsed.password
                    and parsed.path in {"", "/"}
                    and not parsed.query
                    and not parsed.fragment
                )
            except ValueError:
                valid_origin = False
            if not valid_origin:
                errors.append("Every production CORS origin must be a clean HTTPS origin without a path")
                break

    if config.homework_attachments_enabled and not (config.supabase_secret_key or "").strip():
        errors.append("SUPABASE_SECRET_KEY is required when homework attachments are enabled")

    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


settings = Settings()
validate_production_settings(settings)
