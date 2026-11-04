"""ASGI entry point for the SafeRouteZW API."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute

from app.api.errors import install_error_handlers
from app.api.v1 import (
    admin,
    alerts,
    auth,
    blackspots,
    dashboard,
    editorial,
    incidents,
    news,
    processing,
    public,
    public_subscriptions,
    publishing,
    sources,
    summaries,
)
from app.core.config import get_settings

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    """Use the function name as the operation id so generated client names stay readable."""
    return route.name


app = FastAPI(title="SafeRouteZW API", version="0.1.0", generate_unique_id_function=_operation_id)
install_error_handlers(app)

# The browser normally reaches this API through the Next.js same-origin proxy (/backend/*), so
# cookies stay first-party. CORS is only enabled for explicitly listed public origins, never with
# credentials, and never as a wildcard.
app.add_middleware(GZipMiddleware, minimum_size=500)
_public_origins = [o.strip() for o in get_settings().public_cors_origins.split(",") if o.strip()]
if _public_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_public_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
    )
v1 = APIRouter(prefix=API_PREFIX)
v1.include_router(auth.router)
v1.include_router(admin.router)
v1.include_router(dashboard.router)
v1.include_router(news.router)
v1.include_router(sources.router)
v1.include_router(processing.router)
v1.include_router(incidents.router)
v1.include_router(blackspots.router)
v1.include_router(editorial.router)
v1.include_router(publishing.router)
v1.include_router(alerts.router)
v1.include_router(summaries.router)
v1.include_router(public.router)
v1.include_router(public_subscriptions.router)
app.include_router(v1)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health without requiring a database or Ollama connection."""
    return {"status": "ok", "service": "saferoutezw-api", "version": "0.1.0"}
