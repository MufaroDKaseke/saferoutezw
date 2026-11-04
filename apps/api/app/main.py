"""ASGI entry point for the SafeRouteZW API."""

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.api.errors import install_error_handlers
from app.api.v1 import admin, auth, dashboard, incidents, news, processing, sources

API_PREFIX = "/api/v1"


def _operation_id(route: APIRoute) -> str:
    """Use the function name as the operation id so generated client names stay readable."""
    return route.name


app = FastAPI(title="SafeRouteZW API", version="0.1.0", generate_unique_id_function=_operation_id)
install_error_handlers(app)

# No CORS middleware: the browser reaches this API through the Next.js same-origin
# proxy (/backend/*), so cookies stay first-party.
v1 = APIRouter(prefix=API_PREFIX)
v1.include_router(auth.router)
v1.include_router(admin.router)
v1.include_router(dashboard.router)
v1.include_router(news.router)
v1.include_router(sources.router)
v1.include_router(processing.router)
v1.include_router(incidents.router)
app.include_router(v1)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health without requiring a database or Ollama connection."""
    return {"status": "ok", "service": "saferoutezw-api", "version": "0.1.0"}
