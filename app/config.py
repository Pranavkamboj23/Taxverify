from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TaxVerify"
    app_env: str = "development"
    debug: bool = True

    secret_key: str

    database_url: str

    upload_dir: str = "uploads"

    reconciliation_tolerance: float = 1.00

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()