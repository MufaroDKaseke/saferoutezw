"""One error envelope for the whole API: ``{"error": {"code", "message", "details"?}}``.

Handlers never echo SQL, stack traces, parameters or request bodies, so a failure cannot
leak internals or personal data.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """A deliberate, client-safe failure."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def forbidden(message: str = "You do not have permission to do this.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def unauthenticated(message: str = "Sign in to continue.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message)


# Documented in OpenAPI for every authenticated route.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Role not permitted, or CSRF check failed"},
    404: {"model": ErrorResponse, "description": "Record not found"},
    409: {"model": ErrorResponse, "description": "Conflict with current state"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
}

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


def _response(status: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    body = ErrorBody(code=code, message=message, details=details)
    return JSONResponse({"error": body.model_dump(exclude_none=True)}, status_code=status, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return _response(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"),
                "message": str(e.get("msg", "")),
            }
            for e in exc.errors()
        ]
        return _response(422, "VALIDATION_ERROR", "The request was not valid.", details)

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        log.error("Database error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return _response(503, "DATABASE_ERROR", "The database is temporarily unavailable.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return _response(500, "INTERNAL_ERROR", "Something went wrong on our side.")
