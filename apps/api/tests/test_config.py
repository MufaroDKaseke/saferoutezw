import pytest
from pydantic import ValidationError

from app.core.config import REPOSITORY_ROOT, Settings

CONFIG_KEYS = (
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "POSTGRES_DB", "POSTGRES_TEST_DB", "POSTGRES_CONNECT_TIMEOUT",
    "OLLAMA_BASE_URL", "OLLAMA_MODEL", "API_HOST", "API_PORT",
    "RSS_POLL_INTERVAL_SECONDS", "RSS_POLL_ON_STARTUP", "RSS_SCHEDULER_ENABLED",
    "RSS_POLL_MAX_WORKERS",
)


def test_example_configuration_from_another_working_directory(tmp_path, monkeypatch):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=REPOSITORY_ROOT / ".env.example")

    # .env.example holds placeholders only - never real credentials.
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_db == "saferoutezw"
    assert settings.postgres_test_db == "saferoutezw_test"
    assert settings.postgres_user == "<your_postgres_username>"
    assert settings.postgres_password.get_secret_value() == "<your_postgres_password>"
    assert settings.database_url.drivername == "postgresql+psycopg"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.rss_poll_interval_seconds == 180
    assert settings.rss_poll_on_startup is True
    assert settings.rss_scheduler_enabled is True


def test_rss_scheduler_defaults_need_no_configuration(monkeypatch):
    for key in CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.rss_poll_interval_seconds == 180
    assert settings.rss_poll_on_startup is True
    assert settings.rss_scheduler_enabled is True
    assert 1 <= settings.rss_poll_max_workers <= 8


def test_rss_scheduler_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("RSS_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("RSS_POLL_ON_STARTUP", "false")
    monkeypatch.setenv("RSS_SCHEDULER_ENABLED", "false")

    settings = Settings(_env_file=None)

    assert settings.rss_poll_interval_seconds == 60
    assert settings.rss_poll_on_startup is False
    assert settings.rss_scheduler_enabled is False


def test_database_connect_timeout_defaults_to_a_short_bounded_wait(monkeypatch):
    # psycopg on Windows never gives up connecting to a stopped PostgreSQL unless a
    # timeout is set, which would wedge the scheduler's poll cycle forever.
    monkeypatch.delenv("POSTGRES_CONNECT_TIMEOUT", raising=False)
    assert Settings(_env_file=None).postgres_connect_timeout == 5

    monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "2")
    assert Settings(_env_file=None).postgres_connect_timeout == 2

    monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-5", "10"])
def test_rss_poll_interval_below_the_politeness_floor_is_rejected(monkeypatch, value):
    # Every cycle hits ~22 news sites; a typo like 0 or 1 must not turn into a hammer.
    monkeypatch.setenv("RSS_POLL_INTERVAL_SECONDS", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_PORT=8001\n", encoding="utf-8")
    monkeypatch.setenv("API_PORT", "9000")

    assert Settings(_env_file=env_file).api_port == 9000


def test_password_is_not_exposed_by_repr():
    settings = Settings(_env_file=None, postgres_user="u", postgres_password="super-secret")
    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)
