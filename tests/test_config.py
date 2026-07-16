"""Settings load correctly from the environment / `.env`."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, get_settings


def test_loads_database_url_from_env() -> None:
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "filemindr" in settings.database_url


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_storage_path_is_absolute() -> None:
    assert get_settings().storage_path.is_absolute()


def test_env_var_overrides(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@localhost:5432/other")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Bypass the cached instance and the .env file to read the live environment.
    settings = Settings(_env_file=None)
    assert settings.database_url.endswith("/other")
    assert settings.openai_api_key == "sk-test"


def test_defaults_present_without_env(monkeypatch) -> None:
    for key in ("REDIS_URL", "STORAGE_DIR", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.redis_url == "redis://localhost:6379/0"
    assert Path(settings.storage_dir).name == "storage"
