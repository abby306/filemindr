"""Application settings, loaded from the environment / `.env`.

A single `Settings` instance is the source of truth for connection strings,
provider keys, and paths. Secrets live only in `.env` (git-ignored) — never
hardcode them here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (app/core/config.py -> project/).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed view of the process environment.

    Field names map to upper-case env vars (`database_url` <- `DATABASE_URL`),
    matching the keys in `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Datastores
    database_url: str = "postgresql+psycopg://filemindr:localdev@localhost:5432/filemindr"
    redis_url: str = "redis://localhost:6379/0"

    # External providers (blank until set in .env)
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    google_application_credentials: str = "./secrets/vision-credentials.json"

    # Extraction model (DeepSeek, via the OpenAI-compatible client)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Resilience: bounded retry for transient network failures (timeouts/429/5xx).
    retry_max_attempts: int = 3
    retry_base_delay: float = 0.5

    # Max parallel network calls per document (per-chunk extraction, per-page OCR).
    max_parallel_calls: int = 4

    # Reject uploads larger than this (megabytes) before they fill memory/disk.
    max_upload_mb: int = 50

    # Local filesystem + runtime
    storage_dir: str = "./storage"
    app_env: str = "development"

    # Concurrent documents in the OCR→extraction→embedding pipeline. Uploads
    # enqueue instantly; this many process at a time (each chain holds a DB
    # connection and network/CPU resources for its whole run — unbounded, a
    # 30-file drop exhausts the connection pool). 0 = run inline on the
    # caller's thread (tests/CI: deterministic, synchronous).
    pipeline_workers: int = 3

    # Plan-quota enforcement on the write paths (402 when a limit is hit).
    # Off by default: a self-hosted install is unlimited; the hosted product
    # turns this on. Usage metering records regardless (it feeds analytics).
    enforce_quotas: bool = False

    # Pre-load the local embedding + reranker models in a background thread at
    # startup, so the first query doesn't stall ~30-60s on a cold model load.
    # Costs ~400MB RAM up front. Off by default (tests/CI must never load
    # models); set WARMUP_MODELS=true in .env for a running server.
    warmup_models: bool = False

    # CORS — origins allowed to call the API directly from a browser/native app
    # (comma-separated). Dev uses the Next.js same-origin rewrite, so this only
    # matters once the web/native client calls a different origin in prod.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """`cors_origins` split into a list (blank → none)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        """`storage_dir` resolved to an absolute path under the project root."""
        path = Path(self.storage_dir)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def vision_credentials_path(self) -> Path:
        """`google_application_credentials` resolved to an absolute project path."""
        path = Path(self.google_application_credentials)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached `Settings` instance."""
    return Settings()
