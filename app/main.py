"""FastAPI application entry point.

Wires the app, a standard error envelope, an unauthenticated `/health` probe
(which checks DB connectivity), and one authenticated `/api/v1/me` route that
exercises the auth + account-scoping path end to end.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.analytics import router as analytics_router
from app.api.billing import router as billing_router
from app.api.classes import router as classes_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.core.config import get_settings
from app.core.scoping import AccountScope, get_current_account
from app.db.session import engine

settings = get_settings()

app = FastAPI(title="filemindr", version="0.1.0")

# CORS so the web app (and future native client) can call the API directly from
# another origin in production. Bearer auth (not cookies) → no credentials, which
# keeps the header allow-list simple (Authorization + X-Account-Id via "*").
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(documents_router)
app.include_router(conversations_router)
app.include_router(classes_router)
app.include_router(analytics_router)
app.include_router(billing_router)


@app.on_event("startup")
def warmup_models() -> None:
    """Pre-load the local embedder + reranker off the request path.

    Both are lazy singletons that otherwise load on the first query (~30-60s
    cold). A daemon thread warms them so that first answer is fast; failures
    are swallowed — the lazy path still works as before. `WARMUP_MODELS=false`
    skips it (memory-tight hosts, tests).
    """
    if not settings.warmup_models:
        return

    def _warm() -> None:
        try:
            from app.services import embeddings, reranking

            embeddings._get_model()
            reranking._get_model()
        except Exception:  # pragma: no cover — warmup is best-effort
            pass

    import threading

    threading.Thread(target=_warm, name="model-warmup", daemon=True).start()

# Dev-only: serve the throwaway testing UI same-origin (no CORS) at /dev/. Inert in
# any non-development env and when the (git-ignored) dev_ui/ directory is absent.
_dev_ui = Path(__file__).resolve().parent.parent / "dev_ui"
if settings.app_env == "development" and _dev_ui.is_dir():
    app.mount("/dev", StaticFiles(directory=str(_dev_ui), html=True), name="dev_ui")


@app.get("/health", tags=["ops"])
def health() -> JSONResponse:
    """Liveness + DB connectivity. Returns 200 only if `SELECT 1` succeeds."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "env": settings.app_env,
                "database": "down",
                "detail": str(exc.__class__.__name__),
            },
        )
    return JSONResponse(
        content={"status": "ok", "env": settings.app_env, "database": "up"}
    )


@app.get("/api/v1/me", tags=["identity"])
def me(scope: AccountScope = Depends(get_current_account)) -> dict:
    """Return the authenticated user and active account. Gated by auth+scoping."""
    return {
        "user": {"id": str(scope.user.id), "email": scope.user.email},
        "account": {
            "id": str(scope.account.id),
            "type": scope.account.type,
            "name": scope.account.name,
        },
    }
