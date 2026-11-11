"""ASGI entry point for the SafeRouteZW API.

``create_app(settings)`` builds the application for one product mode (``APP_MODE``):

* ``road_safety`` (default): the original SafeRouteZW API, exactly as before.
* ``nust_newsroom``: the NUST FM news monitor. Only authentication, user administration, data sources,
  processing activity and the newsroom API are mounted. Every road-safety route (incidents, blackspots,
  reviews, alerts, publishing, intelligence, the public site API, the WhatsApp webhook) is simply not
  registered, so it answers with the standard 404 and does not appear in the OpenAPI document. The
  road-safety code stays in the repository untouched.
"""

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
    intelligence,
    news,
    newsroom,
    processing,
    public,
    public_subscriptions,
    public_transport,
    publishing,
    sources,
    summaries,
    webhooks,
)
from app.core.config import Settings, get_settings

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    """Use the function name as the operation id so generated client names stay readable."""
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SafeRouteZW API", version="0.1.0", generate_unique_id_function=_operation_id)
    install_error_handlers(app)

    # The browser normally reaches this API through the Next.js same-origin proxy (/backend/*), so
    # cookies stay first-party. CORS is only enabled for explicitly listed public origins, never with
    # credentials, and never as a wildcard.
    app.add_middleware(GZipMiddleware, minimum_size=500)
    public_origins = [o.strip() for o in settings.public_cors_origins.split(",") if o.strip()]
    if public_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=public_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Content-Type", "Authorization"],
        )

    v1 = APIRouter(prefix=API_PREFIX)
    if settings.newsroom_mode:
        routers = (auth.router, admin.router, sources.router, processing.router, newsroom.router)
    else:
        routers = (
            auth.router,
            admin.router,
            dashboard.router,
            news.router,
            sources.router,
            processing.router,
            incidents.router,
            blackspots.router,
            editorial.router,
            publishing.router,
            alerts.router,
            summaries.router,
            intelligence.router,
            public.router,
            public_subscriptions.router,
            public_transport.router,
            webhooks.router,
        )
    for router in routers:
        v1.include_router(router)
    app.include_router(v1)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Report process health without requiring a database or Ollama connection."""
        return {"status": "ok", "service": "saferoutezw-api", "version": "0.1.0"}

    return app


app = create_app()
