from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chikoro Digital API"
    env: str = "development"
    debug: bool = True
    database_url: str = "sqlite:///./chikoro.db"
    secret_key: str = "change-me-in-production-please"
    access_token_expire_minutes: int = 60 * 8
    admin_mfa_required: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    paynow_return_url: str = "http://localhost:3000/paynow/return"
    paynow_result_url: str = "http://localhost:8000/paynow/webhook"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
