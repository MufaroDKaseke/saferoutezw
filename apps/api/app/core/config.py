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
    # Seconds libpq waits per address when connecting. Without it psycopg waits forever
    # for a stopped PostgreSQL on Windows, which would hang a scheduler cycle for good.
    postgres_connect_timeout: int = Field(default=5, ge=1)
    # Destructive integration tests run against this database, never postgres_db.
    postgres_test_db: str = "saferoutezw_test"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    # Local RSS scheduler (python -m app.jobs.scheduler). The floor protects the
    # ~22 news sites polled every cycle from a mistyped interval.
    rss_poll_interval_seconds: int = Field(default=180, ge=30)
    rss_poll_on_startup: bool = True
    rss_scheduler_enabled: bool = True
    rss_poll_max_workers: int = Field(default=4, ge=1, le=8)  # sources fetched in parallel

    # OpenAI incident extraction (app.services.extraction). Without a key the pipeline
    # still screens and fetches articles; it just does not extract.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    # None = use the model's default. Set e.g. 0 for older models; newer ones reject non-default values.
    openai_temperature: float | None = Field(default=None, ge=0, le=2)
    openai_timeout_seconds: float = Field(default=60, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=6)  # SDK retries 429/5xx with backoff

    # Article pipeline (python -m app.jobs.scheduler runs it beside RSS polling).
    pipeline_enabled: bool = True
    pipeline_interval_seconds: int = Field(default=180, ge=30)
    pipeline_batch_size: int = Field(default=25, ge=1, le=200)  # items per stage per cycle
    pipeline_max_attempts: int = Field(default=3, ge=1, le=10)  # fetch / extraction attempts per item
    article_fetch_timeout_seconds: float = Field(default=20, gt=0)
    article_fetch_delay_seconds: float = Field(default=1.0, ge=0)  # pause between requests to one host
    article_max_bytes: int = Field(default=2_000_000, ge=10_000)
    article_min_words: int = Field(default=60, ge=1)  # shorter pages are paywalls/challenges, not articles
    article_max_chars: int = Field(default=24_000, ge=1_000)  # text sent to the model (head of article)
    extraction_min_confidence: float = Field(default=0.6, ge=0, le=1)

    # Authentication (server-side sessions in PostgreSQL, HTTP-only cookie).
    session_cookie_name: str = "srz_session"
    session_ttl_minutes: int = Field(default=480, ge=5)  # sliding: refreshed while the user is active
    session_absolute_max_hours: int = Field(default=24, ge=1)
    cookie_secure: bool = False  # set true when served over HTTPS
    cookie_samesite: str = Field(default="lax", pattern="^(lax|strict)$")
    login_max_failures: int = Field(default=5, ge=1)  # per e-mail or per address within the window
    login_window_minutes: int = Field(default=15, ge=1)
    # Origins allowed to send state-changing requests (checked against Origin/Referer).
    trusted_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Geolocation. "google" needs GOOGLE_MAPS_API_KEY; "none" leaves every incident unresolved.
    geocoder: str = Field(default="google", pattern="^(google|none)$")
    google_maps_api_key: SecretStr | None = None
    geocoder_timeout_seconds: float = Field(default=10, gt=0)
    # A single result only counts as "resolved" when its bounding box is at most this wide.
    geocode_max_precision_m: float = Field(default=1500, gt=0)
    blackspot_match_radius_m: float = Field(default=500, gt=0)

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
