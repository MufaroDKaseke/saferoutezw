"""Fetch and read the full article behind an RSS entry.

Reuses the existing page parser (``feeds.extract_page``: JSON-LD, Open Graph, body
selectors, paragraph-density fallback). What this module adds is the safety a
server-side fetch of attacker-influenced URLs needs:

* http(s) only; every redirect hop is re-validated;
* private, loopback, link-local and reserved addresses are refused (SSRF);
* the response is size-capped while streaming and must be HTML;
* sites that sit behind captcha / Cloudflare challenges are not fetched at all, and
  challenge pages that slip through fail the minimum-length check instead of being
  mistaken for articles. We never try to bypass bot protection.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import requests

from app.ingestion.feeds import USER_AGENT, extract_page

MAX_REDIRECTS = 5

# Hosts that serve captcha / Cloudflare challenges to non-browser clients (see
# feeds.BLOCKED). Respected, not circumvented.
BLOCKED_HOSTS = frozenset(
    {"newzimbabwe.com", "zimlive.com", "hararelive.com", "chronicle.co.zw", "manicapost.co.zw"}
)


class ArticleFetchError(Exception):
    """The article could not be retrieved or read.

    ``transient`` errors (timeouts, 5xx, 429) are worth retrying later; the rest
    (404, blocked site, not HTML, too short) will not improve.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass
class ArticleText:
    url: str
    text: str
    title: str = ""
    published: str | None = None
    authors: list[str] = field(default_factory=list)
    language: str = ""
    word_count: int = 0


ArticleFetchFn = Callable[[str], ArticleText]


def _host_blocked(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS)


def _check_public_host(host: str) -> None:
    """Refuse hosts that resolve to non-public addresses."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ArticleFetchError(f"cannot resolve host {host}", transient=True) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ArticleFetchError(f"refusing non-public address for {host}")


class ArticleFetcher:
    """Stateful so it can pause between requests to the same site."""

    def __init__(
        self,
        *,
        timeout: float = 20,
        delay: float = 1.0,
        max_bytes: int = 2_000_000,
        min_words: int = 60,
        allow_private_hosts: bool = False,  # tests fetch from a localhost server
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout
        self._delay = delay
        self._max_bytes = max_bytes
        self._min_words = min_words
        self._allow_private = allow_private_hosts
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self._last_hit: dict[str, float] = {}

    def __call__(self, url: str) -> ArticleText:
        return self.fetch(url)

    def fetch(self, url: str) -> ArticleText:
        html, final_url = self._download(url)
        page = extract_page(html, final_url)
        text = page["content_text"].strip()
        words = len(text.split())
        if words < self._min_words:
            raise ArticleFetchError(
                f"article text too short ({words} words): paywall, challenge page or unsupported layout"
            )
        return ArticleText(
            url=final_url,
            text=text,
            title=page.get("title", ""),
            published=page.get("published"),
            authors=page.get("authors", []),
            language=page.get("language", ""),
            word_count=words,
        )

    # -- internals ---------------------------------------------------------------
    def _validate(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ArticleFetchError(f"unsupported URL scheme or host: {parts.scheme or 'none'}")
        host = parts.hostname
        if _host_blocked(host):
            raise ArticleFetchError(f"{host} serves bot-protection challenges; not fetched")
        if not self._allow_private:
            _check_public_host(host)
        return host

    def _pause(self, host: str) -> None:
        wait = self._last_hit.get(host, 0.0) + self._delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _download(self, url: str) -> tuple[str, str]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host = self._validate(current)
            self._pause(host)
            try:
                response = self._session.get(
                    current, timeout=self._timeout, stream=True, allow_redirects=False
                )
            except requests.Timeout as exc:
                raise ArticleFetchError("timed out fetching article", transient=True) from exc
            except requests.RequestException as exc:
                raise ArticleFetchError(f"request failed: {type(exc).__name__}", transient=True) from exc
            try:
                if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise ArticleFetchError("redirect without Location header")
                    current = urljoin(current, location)
                    continue
                status = response.status_code
                if status == 429 or status >= 500:
                    raise ArticleFetchError(f"HTTP {status}", transient=True)
                if status >= 400 or status == 202:  # 202: captcha interstitial seen on some hosts
                    raise ArticleFetchError(f"HTTP {status}")
                content_type = response.headers.get("Content-Type", "").lower()
                if "html" not in content_type and "xml" not in content_type:
                    raise ArticleFetchError(f"not an HTML page ({content_type or 'no content type'})")
                body = self._read_capped(response)
                return body.decode(response.encoding or response.apparent_encoding or "utf-8", "replace"), current
            finally:
                response.close()
        raise ArticleFetchError("too many redirects")

    def _read_capped(self, response: requests.Response) -> bytes:
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65_536):
            size += len(chunk)
            if size > self._max_bytes:
                raise ArticleFetchError(f"page larger than {self._max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
