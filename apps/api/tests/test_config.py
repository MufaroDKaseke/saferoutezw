from app.core.config import REPOSITORY_ROOT, Settings

CONFIG_KEYS = (
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "POSTGRES_DB", "POSTGRES_TEST_DB",
    "OLLAMA_BASE_URL", "OLLAMA_MODEL", "API_HOST", "API_PORT",
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


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_PORT=8001\n", encoding="utf-8")
    monkeypatch.setenv("API_PORT", "9000")

    assert Settings(_env_file=env_file).api_port == 9000


def test_password_is_not_exposed_by_repr():
    settings = Settings(_env_file=None, postgres_user="u", postgres_password="super-secret")
    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)
