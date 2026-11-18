"""Opt-in Google News article resolution; ordinary article fetching is delegated unchanged.

Google's opaque IDs require the article's signature/timestamp and the Fbv4je
``garturlreq`` RPC (protocol reference: SSujitX/google-news-url-decoder).
Keep that undocumented protocol here, fail closed if it changes, and never parse
the intermediary as an article. No browser, proxy rotation or challenge bypass.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from app.ingestion.article import ArticleFetchError, ArticleFetchFn, ArticleFetcher, ArticleText, MAX_REDIRECTS

_ARTICLE_PATH = re.compile(r"/(?:rss/articles|articles|read)/([A-Za-z0-9_-]{1,2048})/?\Z")
_RPC_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
# Google's request context, shared by the public Google News decoder implementations.
_RPC_CONTEXT = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
    "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
]


def is_google_news_url(url: str | None) -> bool:
    """Exact parsed hostname, never a substring match or a publisher allowlist."""
    try:
        return bool(url) and urlsplit(url).hostname == "news.google.com"
    except ValueError:
        return False


def _url_parts(url: str):
    try:
        if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
            raise ValueError
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.port not in {None, 443 if parts.scheme == "https" else 80}):
            raise ValueError
        return parts
    except ValueError as exc:
        raise ArticleFetchError("invalid Google News or publisher HTTP(S) URL") from exc


def _publisher_url(url: str) -> str:
    host = _url_parts(url).hostname.lower().rstrip(".")
    if host == "google.com" or host.endswith(".google.com"):
        raise ArticleFetchError("unresolved Google News intermediary or consent page")
    return url


class _PublicHTTPAdapter(HTTPAdapter):
    """Pin each connection to a checked public IP, retaining TLS SNI/verification.

    Validation followed by an ordinary second DNS lookup permits DNS rebinding.
    This adapter is used only by Google resolution and its publisher requests.
    """

    def send(self, request, **kwargs):
        parts = _url_parts(request.url)
        if kwargs.get("proxies"):
            raise ArticleFetchError("proxies are not supported for Google News resolution")
        request.headers["Host"] = parts.netloc
        return super().send(request, **kwargs)

    def _public_pool(self, url, pool_kwargs=None):
        parts = _url_parts(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ArticleFetchError("cannot resolve article host", transient=True) from exc
        if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
            raise ArticleFetchError("refusing non-public article destination")
        options = dict(pool_kwargs or {})
        if parts.scheme == "https":
            options.update(server_hostname=parts.hostname, assert_hostname=parts.hostname)
        return self.poolmanager.connection_from_host(
            addresses[0][4][0], port=port, scheme=parts.scheme, pool_kwargs=options,
        )

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        _, options = self.build_connection_pool_key_attributes(request, verify, cert)
        return self._public_pool(request.url, options)

    def get_connection(self, url, proxies=None):  # Requests 2.31 compatibility
        return self._public_pool(url)


def _public_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # no ambient proxies, netrc credentials or automatic retries
    session.mount("https://", _PublicHTTPAdapter())
    session.mount("http://", _PublicHTTPAdapter())
    return session


def _reject_error_page(html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if any(marker in html.lower() for marker in ("/cdn-cgi/challenge-platform/", "cf-chl-", "cf_chl_")):
        raise ArticleFetchError("access restricted: bot-protection challenge")
    if re.match(r"^(just a moment|attention required|access denied|403 forbidden|captcha)(?:\b|$)", title):
        raise ArticleFetchError("access restricted: challenge or access-denied page")
    if re.match(r"^(404|page not found|not found|500|502|503|server error|service unavailable)(?:\b|$)", title):
        raise ArticleFetchError("publisher returned an error page")


class _PublisherFetcher(ArticleFetcher):
    def _validate(self, url: str) -> str:
        _publisher_url(url)  # also checked on every publisher redirect, before any request
        return super()._validate(url)

    def _download(self, url: str) -> tuple[str, str]:
        html, final_url = super()._download(url)
        _reject_error_page(html)
        if "data-n-a-sg=" in html or "<title>Google News" in html:
            raise ArticleFetchError("unresolved Google News intermediary HTML")
        return html, final_url


class GoogleNewsResolver(ArticleFetcher):
    """Bounded GET redirects, then Google's signature-based lookup if necessary."""

    def __init__(self, **options) -> None:
        if "session" not in options:
            options["session"] = _public_session()
        super().__init__(**options)

    def _request(self, method: str, url: str, **kwargs) -> tuple[str, str | None]:
        parts = _url_parts(url)
        if parts.hostname != "news.google.com":
            raise ArticleFetchError("Google News lookup left its exact hostname")
        self._pause(self._validate(url))
        try:
            response = self._session.request(
                method, url, timeout=self._timeout, stream=True, allow_redirects=False, **kwargs,
            )
            try:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if method != "GET" or not location:
                        raise ArticleFetchError("unexpected Google News lookup redirect")
                    return "", urljoin(url, location)
                if not 200 <= status < 300 or status == 202:
                    raise ArticleFetchError(f"Google News HTTP {status}", transient=status == 429 or status >= 500)
                body = self._read_capped(response)
                return body.decode(response.encoding or "utf-8", "replace"), None
            finally:
                response.close()
        except requests.Timeout as exc:
            raise ArticleFetchError("Google News resolution timed out", transient=True) from exc
        except requests.RequestException as exc:
            raise ArticleFetchError("Google News lookup request failed", transient=True) from exc

    def resolve(self, url: str) -> str:
        parts = _url_parts(url)
        match = _ARTICLE_PATH.fullmatch(parts.path)
        if parts.hostname != "news.google.com" or not match:
            raise ArticleFetchError("invalid Google News article-link path")
        query = parse_qs(parts.query)
        locale = {key: query.get(key, [default])[0] for key, default in (("hl", "en"), ("gl", "ZW"), ("ceid", "ZW:en"))}
        current = "https://news.google.com/rss/articles/" + match[1] + "?" + urlencode(locale)
        for _ in range(MAX_REDIRECTS + 1):
            html, redirect = self._request("GET", current)
            if redirect:
                _url_parts(redirect)
                if not is_google_news_url(redirect):
                    return self._destination(redirect)
                if not _ARTICLE_PATH.fullmatch(urlsplit(redirect).path):
                    raise ArticleFetchError("unresolved Google News redirect")
                current = redirect
                continue
            _reject_error_page(html)
            node = BeautifulSoup(html, "html.parser").select_one("[data-n-a-sg][data-n-a-ts]")
            if node is None:
                raise ArticleFetchError("unresolved Google News article: missing resolution signature")
            signature, timestamp = node.get("data-n-a-sg", ""), node.get("data-n-a-ts", "")
            if not signature or len(signature) > 4096 or not timestamp.isdigit() or not 0 < int(timestamp) < 2**63:
                raise ArticleFetchError("invalid Google News resolution signature")
            token = _ARTICLE_PATH.fullmatch(urlsplit(current).path)[1]
            request = ["garturlreq", _RPC_CONTEXT, token, int(timestamp), signature]
            payload = json.dumps([[["Fbv4je", json.dumps(request), None, "0"]]])
            body, _ = self._request("POST", _RPC_URL, data={"f.req": payload})
            # Google returns XSSI-prefixed, sometimes length-framed JSON records.
            body = body.lstrip().removeprefix(")]}'").strip()
            for candidate in [body, *body.splitlines()]:
                try:
                    records = json.loads(candidate)
                    for record in records:
                        if isinstance(record, list) and len(record) >= 3 and record[:2] == ["wrb.fr", "Fbv4je"]:
                            result = json.loads(record[2])
                            if isinstance(result, list) and len(result) >= 2 and result[0] == "garturlres" and isinstance(result[1], str):
                                return self._destination(result[1])
                except (ValueError, TypeError):
                    continue
            raise ArticleFetchError("unresolved Google News article: invalid lookup response")
        raise ArticleFetchError("too many Google News redirects")

    def _destination(self, url: str) -> str:
        _publisher_url(url)
        self._validate(url)
        return url


class GoogleNewsFetchError(ArticleFetchError):
    def __init__(self, error: ArticleFetchError, metadata: dict[str, str]) -> None:
        message = str(error)
        if metadata["status"] == "access_restricted" and "access restricted" not in message:
            message = "access restricted: " + message
        super().__init__(message, transient=error.transient)
        self.google_news = metadata


class GoogleNewsArticleFetcher:
    """Ordinary URLs take the original path; Google URLs resolve or fail closed."""

    def __init__(self, ordinary: ArticleFetchFn, *, enabled: bool = False, resolver=None, publisher=None, **options) -> None:
        self._ordinary, self._enabled = ordinary, enabled
        self._resolver, self._publisher, self._options = resolver, publisher, options

    def __call__(self, url: str) -> ArticleText:
        if not is_google_news_url(url):
            return self._ordinary(url)
        metadata = {"status": "unresolved", "original_url": url}
        try:
            if not self._enabled:
                raise ArticleFetchError("Google News resolution disabled")
            if self._resolver is None:
                self._resolver = GoogleNewsResolver(**self._options)
            destination = self._resolver.resolve(url)
            _publisher_url(destination)
            metadata["resolved_url"] = destination
            if self._publisher is None:
                self._publisher = _PublisherFetcher(session=_public_session(), **self._options)
            return self._publisher(destination)
        except ArticleFetchError as exc:
            if any(marker in str(exc) for marker in ("HTTP 403", "access restricted", "bot-protection")):
                metadata["status"] = "access_restricted"
            raise GoogleNewsFetchError(exc, metadata) from exc
        except requests.RequestException as exc:
            error = ArticleFetchError("publisher request timed out or failed", transient=True)
            raise GoogleNewsFetchError(error, metadata) from exc
