"""ASGI entry point for the SafeRouteZW API."""

from fastapi import FastAPI

app = FastAPI(title="SafeRouteZW API", version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report process health without requiring a database or Ollama connection."""
    return {"status": "ok", "service": "saferoutezw-api", "version": "0.1.0"}
