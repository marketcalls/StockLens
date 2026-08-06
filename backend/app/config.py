"""Application configuration, loaded from environment and .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Environments served over plain HTTP, where a Secure cookie would never be
# sent back by the browser or the test client.
PLAIN_HTTP_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing", "local"})


class Settings(BaseSettings):
    """Runtime configuration.

    The FinEdge key is held as a SecretStr so that an accidental repr or log
    interpolation prints '**********' rather than the credential.
    """

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    finedge_api_key: SecretStr = Field(default=SecretStr(""))
    finedge_base_url: str = "https://data.finedgeapi.com"
    finedge_max_rps: float = 5.0
    finedge_timeout_seconds: float = 60.0
    finedge_max_retries: int = 4

    stocklens_db_path: Path = Path("data/stocklens.db")
    stocklens_raw_db_path: Path = Path("data/stocklens_raw.db")

    jwt_secret: SecretStr = SecretStr("dev_only_change_me")
    jwt_expiry_minutes: int = 10080

    environment: str = "development"
    cors_origins: str = "http://localhost:5173"
    # Whether the session cookie carries Secure. Left as None it is derived from
    # `environment`. Inferring it from a free-text name is fragile - a third
    # value such as "test" silently got a Secure cookie that cannot travel over
    # HTTP, so the name is matched against an explicit set of plain-HTTP
    # environments rather than against one string.
    cookie_secure: bool | None = None

    @field_validator("stocklens_db_path", "stocklens_raw_db_path")
    @classmethod
    def _resolve_against_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment.lower() not in PLAIN_HTTP_ENVIRONMENTS

    @property
    def has_finedge_key(self) -> bool:
        return bool(self.finedge_api_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
