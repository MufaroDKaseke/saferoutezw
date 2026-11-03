from app.core.config import REPOSITORY_ROOT, Settings


def test_example_configuration_from_another_working_directory(tmp_path, monkeypatch):
    for key in (
        "DATABASE_URL", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "API_HOST", "API_PORT"
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=REPOSITORY_ROOT / ".env.example")

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_PORT=8001\n", encoding="utf-8")
    monkeypatch.setenv("API_PORT", "9000")

    assert Settings(_env_file=env_file).api_port == 9000
