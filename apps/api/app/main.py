"""ASGI entry point for the SafeRouteZW API."""

from fastapi import APIRouter, FastAPI

from app.api.errors import install_error_handlers
from app.api.v1 import admin, auth

API_PREFIX = "/api/v1"

app = FastAPI(title="SafeRouteZW API", version="0.1.0")
install_error_handlers(app)

# No CORS middleware: the browser reaches this API through the Next.js same-origin
# proxy (/backend/*), so cookies stay first-party.
v1 = APIRouter(prefix=API_PREFIX)
v1.include_router(auth.router)
v1.include_router(admin.router)
app.include_router(v1)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health without requiring a database or Ollama connection."""
    return {"status": "ok", "service": "saferoutezw-api", "version": "0.1.0"}
