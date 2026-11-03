"""Load local configuration independently of the working directory."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

DRIVERNAME = "postgresql+psycopg"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str | None = None
    postgres_password: SecretStr | None = None
    postgres_db: str = "saferoutezw"
    # Destructive integration tests run against this database, never postgres_db.
    postgres_test_db: str = "saferoutezw_test"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    def build_database_url(self, database: str | None = None) -> URL:
        """Build the SQLAlchemy URL; ``URL.create`` handles special characters.

        Settings load without credentials so ``/health`` works without a
        database; the error is raised only when a connection is requested.
        """
        if not self.postgres_user or self.postgres_password is None:
            raise RuntimeError(
                "Set POSTGRES_USER and POSTGRES_PASSWORD in the root .env file "
                "before using the database."
            )
        return URL.create(
            DRIVERNAME,
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=database or self.postgres_db,
        )

    @property
    def database_url(self) -> URL:
        return self.build_database_url()

    @property
    def test_database_url(self) -> URL:
        return self.build_database_url(self.postgres_test_db)


@lru_cache
def get_settings() -> Settings:
    return Settings()
