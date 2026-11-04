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
    # Cost control: comma-separated primary categories worth fetching and classifying (e.g.
    # "road_incident,traffic_disruption"). Empty means every category in the taxonomy.
    intelligence_categories_enabled: str = ""

    # Social media ingestion through Apify (app.ingestion.social). OFF by default: it spends
    # money, so it needs an explicit switch *and* a token. Only allow-listed accounts are read.
    apify_api_token: SecretStr | None = None
    social_ingestion_enabled: bool = False
    social_poll_check_seconds: int = Field(default=300, ge=60)  # how often the scheduler looks for due accounts
    social_run_timeout_seconds: int = Field(default=600, ge=60, le=3600)  # hard stop for one Actor run
    social_max_charge_usd_per_run: float = Field(default=0.25, gt=0)  # Apify stops the run at this spend
    social_max_runs_per_day: int = Field(default=24, ge=1)  # Actor runs per rolling 24 h, all accounts
    social_first_run_lookback_hours: int = Field(default=48, ge=1, le=336)  # window for an account's first poll
    social_retry_after_error_minutes: int = Field(default=30, ge=1)  # a failed poll is retried sooner than the interval
    social_post_max_chars: int = Field(default=8000, ge=500)  # longer posts are truncated before storage

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

    # Geolocation. "geoapify" needs GEOAPIFY_API_KEY, "google" needs GOOGLE_MAPS_API_KEY;
    # "none" leaves every incident unresolved.
    geocoder: str = Field(default="geoapify", pattern="^(geoapify|google|none)$")
    google_maps_api_key: SecretStr | None = None
    geocoder_timeout_seconds: float = Field(default=10, gt=0)
    # A single result only counts as "resolved" when its bounding box is at most this wide.
    geocode_max_precision_m: float = Field(default=1500, gt=0)
    blackspot_match_radius_m: float = Field(default=500, gt=0)
    # Incidents clustered like this become a derived blackspot: at least this many within the radius.
    blackspot_cluster_radius_m: float = Field(default=1000, gt=0)
    blackspot_cluster_min_incidents: int = Field(default=3, ge=2)

    # Public API hardening.
    public_cors_origins: str = ""  # comma-separated origins allowed to call /api/v1/public from a browser
    public_rate_limit_per_minute: int = Field(default=120, ge=1)  # read endpoints, per client address
    public_write_rate_limit_per_minute: int = Field(default=10, ge=1)  # subscription / planning endpoints
    trust_forwarded_for: bool = False  # honour X-Forwarded-For (only behind a trusted proxy)

    # Route planning and place search. "geoapify" needs GEOAPIFY_API_KEY; "mock" is for tests only.
    routing_provider: str = Field(default="geoapify", pattern="^(geoapify|mock|none)$")
    geoapify_api_key: SecretStr | None = None
    routing_timeout_seconds: float = Field(default=10, gt=0)
    route_hazard_buffer_m: float = Field(default=2000, gt=0, le=20000)

    # Phone subscriptions. Keys must be set in production; development derives a clearly
    # insecure fallback so the mock flow works without configuration.
    subscriber_encryption_key: SecretStr | None = None  # Fernet key (urlsafe base64, 32 bytes)
    subscriber_digest_key: SecretStr | None = None
    notification_provider: str = Field(default="mock", pattern="^(mock|whatsapp_meta)$")
    # LOCAL DEMO ONLY: with the mock provider, return the one-time code in the API response so the
    # flow can be tried without a phone. Never enable alongside a real provider.
    mock_expose_codes: bool = False
    # Major road corridors offered for alerts, comma separated (matched against the alert road name).
    subscription_corridors: str = ""
    otp_ttl_seconds: int = Field(default=600, ge=60)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=0)
    otp_max_per_hour: int = Field(default=5, ge=1)
    management_token_ttl_minutes: int = Field(default=30, ge=5)
    notification_max_attempts: int = Field(default=3, ge=1, le=10)

    # WhatsApp bot (Meta WhatsApp Business Cloud API). OFF and in mock-sending mode by default:
    # nothing is sent to a real phone until WHATSAPP_SEND_MODE=live *and* credentials are set.
    whatsapp_enabled: bool = False
    whatsapp_provider: str = Field(default="meta_cloud", pattern="^meta_cloud$")
    whatsapp_send_mode: str = Field(default="mock", pattern="^(mock|live)$")
    whatsapp_access_token: SecretStr | None = None
    whatsapp_app_secret: SecretStr | None = None  # signs inbound webhooks (X-Hub-Signature-256)
    whatsapp_verify_token: SecretStr | None = None  # echoed back during webhook subscription
    whatsapp_phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None
    whatsapp_graph_api_version: str = Field(default="v23.0", pattern=r"^v\d+\.\d+$")
    whatsapp_api_timeout_seconds: float = Field(default=10, gt=0)
    whatsapp_api_max_retries: int = Field(default=2, ge=0, le=5)
    whatsapp_alert_template_name: str | None = None  # approved template for proactive alerts
    whatsapp_alert_template_language: str = "en"
    whatsapp_session_ttl_minutes: int = Field(default=30, ge=1)  # idle conversation is reset after this
    whatsapp_user_msgs_per_minute: int = Field(default=20, ge=1)  # per sender, above this is dropped
    whatsapp_dispatch_interval_seconds: int = Field(default=15, ge=5)
    whatsapp_dispatch_batch_size: int = Field(default=50, ge=1, le=500)
    whatsapp_max_attempts: int = Field(default=3, ge=1, le=10)  # processing attempts per inbound message
    whatsapp_retention_days: int = Field(default=30, ge=1)  # processed inbound payloads are cleared after this
    public_web_base_url: str = "http://localhost:3000"  # for links in bot replies

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
