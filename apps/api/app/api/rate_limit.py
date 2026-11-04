"""Small in-process sliding-window rate limiter for the public API.

Per client address and bucket. It protects a single API process; behind several workers each
keeps its own window (acceptable for this MVP; put a shared limiter at the edge for scale).
Subscription abuse is additionally limited per phone number in the database (see
``app.services.subscriptions``).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import ApiError
from app.core.config import Settings, get_settings

_WINDOW_SECONDS = 60.0
_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def check_rate_limit(bucket: str, key: str, limit: int, *, now: float | None = None) -> None:
    moment = time.monotonic() if now is None else now
    with _lock:
        window = _hits[(bucket, key)]
        while window and moment - window[0] >= _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit:
            retry = max(1, int(_WINDOW_SECONDS - (moment - window[0])))
            raise ApiError(
                429,
                "RATE_LIMITED",
                "Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )
        window.append(moment)


def limiter(bucket: str, *, write: bool) -> Callable[..., None]:
    def dependency(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
        limit = settings.public_write_rate_limit_per_minute if write else settings.public_rate_limit_per_minute
        check_rate_limit(bucket, client_ip(request, settings), limit)

    return dependency


ReadLimit = Depends(limiter("public-read", write=False))
WriteLimit = Depends(limiter("public-write", write=True))
