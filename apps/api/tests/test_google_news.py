"""Synthetic Google protocol fixtures; no live Google/publisher requests or AI calls."""

import io
import ipaddress
import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from app.core.config import Settings
from app.ingestion.article import ArticleFetchError, ArticleFetcher
from app.ingestion.google_news import (
    GoogleNewsArticleFetcher, GoogleNewsFetchError, GoogleNewsResolver,
    _PublicHTTPAdapter, _PublisherFetcher, _public_session,
)
from feed_server import article_page

GOOGLE = "https://news.google.com/rss/articles/CBMi_test?hl=en&gl=ZW&ceid=ZW:en"
PUBLISHER = "https://www.techzim.co.zw/2026/11/example-story/"
SIGNATURE = '<c-wiz><div data-n-a-sg="test-signature" data-n-a-ts="1794900000"></div></c-wiz>'
BODY = "The newsroom reported the budget debate and explained the figures in detail. " * 12


def response(body="", status=200, **headers):
    result = requests.Response()
    result.status_code = status
    result.headers.update({"Content-Type": "text/html; charset=utf-8", **headers})
    result.encoding = "utf-8"
    result.raw = io.BytesIO(body.encode())
    return result


def rpc_response(url=PUBLISHER, *, framed=False):
    rows = [["wrb.fr", "Fbv4je", json.dumps(["garturlres", url]), None, "0"]]
    body = json.dumps(rows)
    return response(")]}'\n\n" + (str(len(body)) + "\n" if framed else "") + body)


class Session(requests.Session):
    def __init__(self, *replies):
        super().__init__()
        self.replies, self.calls = list(replies), []

    def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url, kwargs))
        if not self.replies:
            raise AssertionError("Unexpected HTTP request: " + url)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def public_dns(monkeypatch):
    real_lookup = socket.getaddrinfo
    def lookup(host, port, *args, **kwargs):
        if host == "localhost":  # leave the disposable PostgreSQL connection on its real address
            return real_lookup(host, port, *args, **kwargs)
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = "10.0.0.7" if host == "internal.example" else "93.184.216.34"
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port or 0))]
    monkeypatch.setattr(socket, "getaddrinfo", lookup)


def resolver(session):
    return GoogleNewsResolver(session=session, delay=0, timeout=2)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("url", [
    PUBLISHER,
    "https://news.google.com.publisher.example/rss/articles/CBMi_test",
    "https://publisher.example/article?url=https://news.google.com/rss/articles/CBMi_test",
])
def test_ordinary_urls_delegate_unchanged_and_never_call_the_resolver(enabled, url):
    ordinary, resolve = Mock(), Mock(side_effect=AssertionError("resolver must not run"))
    wrapped = GoogleNewsArticleFetcher(ordinary, enabled=enabled, resolver=SimpleNamespace(resolve=resolve))
    assert wrapped(url) is ordinary.return_value
    ordinary.assert_called_once_with(url)
    resolve.assert_not_called()


def test_ordinary_fetch_errors_are_the_original_exception():
    error = ArticleFetchError("ordinary timeout", transient=True)
    ordinary = Mock(side_effect=error)
    with pytest.raises(ArticleFetchError) as caught:
        GoogleNewsArticleFetcher(ordinary, enabled=True)(PUBLISHER)
    assert caught.value is error


def test_a_normal_article_uses_the_real_original_fetch_path(feed_server):
    url = feed_server.serve_html("/normal", article_page("Budget", [BODY]))
    original = ArticleFetcher(allow_private_hosts=True, delay=0)
    wrapped = GoogleNewsArticleFetcher(original, enabled=True)
    assert wrapped(url) == original(url)
    assert feed_server.hits["/normal"] == 2
    assert wrapped._resolver is None and wrapped._publisher is None


def test_resolution_is_opt_in_and_disabled_google_never_becomes_article_html():
    assert Settings(_env_file=None).google_news_resolution_enabled is False
    ordinary, resolve = Mock(), Mock()
    wrapped = GoogleNewsArticleFetcher(ordinary, resolver=SimpleNamespace(resolve=resolve))
    with pytest.raises(GoogleNewsFetchError, match="disabled") as caught:
        wrapped(GOOGLE)
    assert caught.value.google_news == {"status": "unresolved", "original_url": GOOGLE}
    ordinary.assert_not_called()
    resolve.assert_not_called()


@pytest.mark.parametrize("path", ["rss/articles", "articles", "read"])
@pytest.mark.parametrize("framed", [False, True])
def test_signature_lookup_resolves_the_exact_publisher_url(public_dns, path, framed):
    session = Session(response(SIGNATURE), rpc_response(framed=framed))
    url = GOOGLE.replace("rss/articles", path)
    assert resolver(session).resolve(url) == PUBLISHER
    assert [call[0] for call in session.calls] == ["GET", "POST"]
    get_url = urlsplit(session.calls[0][1])
    assert get_url.hostname == "news.google.com" and get_url.path == "/rss/articles/CBMi_test"
    assert parse_qs(get_url.query) == {"hl": ["en"], "gl": ["ZW"], "ceid": ["ZW:en"]}
    envelope = json.loads(session.calls[1][2]["data"]["f.req"])[0][0]
    assert envelope[0] == "Fbv4je"
    assert json.loads(envelope[1])[2:] == ["CBMi_test", 1794900000, "test-signature"]
    assert all(call[2]["allow_redirects"] is False and call[2]["timeout"] == 2 for call in session.calls)


def test_a_legitimate_publisher_redirect_needs_no_rpc(public_dns):
    session = Session(response(status=302, Location=PUBLISHER))
    assert resolver(session).resolve(GOOGLE) == PUBLISHER
    assert len(session.calls) == 1


def test_google_redirects_are_bounded_and_relative_locations_work(public_dns):
    session = Session(response(status=301, Location="/read/CBMi_second"), response(SIGNATURE), rpc_response())
    assert resolver(session).resolve(GOOGLE) == PUBLISHER
    envelope = json.loads(session.calls[-1][2]["data"]["f.req"])[0][0]
    assert json.loads(envelope[1])[2] == "CBMi_second"
    loop = Session(*[response(status=302, Location=GOOGLE) for _ in range(6)])
    with pytest.raises(ArticleFetchError, match="too many"):
        resolver(loop).resolve(GOOGLE)
    assert len(loop.calls) == 6


@pytest.mark.parametrize("url", [
    "https://news.google.com/rss/search?q=anything",
    "https://news.google.com/", "https://news.google.com/rss/articles/",
    "https://news.google.com/rss/articles/a/b", "https://news.google.com/rss/articles/a%2Fb",
    "https://user:pass@news.google.com/rss/articles/test",
    "https://news.google.com:444/rss/articles/test", "ftp://news.google.com/rss/articles/test",
    "https://news.google.com/rss/articles/test\\evil", "https://news.google.com/rss/articles/test\n",
    "https://news.google.com.publisher.example/rss/articles/test",
])
def test_invalid_google_urls_fail_before_requests(url):
    session = Session()
    with pytest.raises(ArticleFetchError):
        resolver(session).resolve(url)
    assert session.calls == []


@pytest.mark.parametrize("destination", [
    "http://127.0.0.1/", "http://10.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://internal.example/", "file:///etc/passwd", "javascript:alert(1)",
    "https://user:pass@publisher.example/story", "https://publisher.example:8443/story",
    "https://consent.google.com/m", GOOGLE,
])
def test_decoded_destinations_cannot_be_private_invalid_or_google_intermediaries(public_dns, destination):
    session = Session(response(SIGNATURE), rpc_response(destination))
    with pytest.raises(ArticleFetchError):
        resolver(session).resolve(GOOGLE)
    assert len(session.calls) == 2


def test_a_private_redirect_is_not_requested(public_dns):
    session = Session(response(status=302, Location="http://169.254.169.254/"))
    with pytest.raises(ArticleFetchError, match="non-public"):
        resolver(session).resolve(GOOGLE)
    assert len(session.calls) == 1


@pytest.mark.parametrize("body", ["not json", "null", "{}", "[]", '[["wrb.fr","Fbv4je",null]]'])
def test_malformed_rpc_fails_closed(public_dns, body):
    with pytest.raises(ArticleFetchError, match="unresolved"):
        resolver(Session(response(SIGNATURE), response(body))).resolve(GOOGLE)


def test_google_html_without_a_signature_is_never_treated_as_article_content(public_dns):
    session = Session(response(article_page("Google News", [BODY])))
    ordinary, publisher = Mock(), Mock()
    wrapped = GoogleNewsArticleFetcher(ordinary, enabled=True, resolver=resolver(session), publisher=publisher)
    with pytest.raises(GoogleNewsFetchError, match="missing resolution signature"):
        wrapped(GOOGLE)
    ordinary.assert_not_called()
    publisher.assert_not_called()


@pytest.mark.parametrize("stage", ["google_get", "google_rpc", "publisher"])
def test_timeouts_are_bounded_transient_article_errors(public_dns, stage):
    replies = [requests.Timeout()] if stage == "google_get" else [response(SIGNATURE), requests.Timeout()]
    if stage == "publisher":
        replies = [response(SIGNATURE), rpc_response()]
    publisher = _PublisherFetcher(session=Session(requests.Timeout()), delay=0)
    wrapped = GoogleNewsArticleFetcher(Mock(), enabled=True, resolver=resolver(Session(*replies)), publisher=publisher)
    with pytest.raises(GoogleNewsFetchError) as caught:
        wrapped(GOOGLE)
    assert caught.value.transient is True and caught.value.google_news["status"] == "unresolved"


@pytest.mark.parametrize("status", [403, 404, 429, 503])
def test_google_http_errors_do_not_produce_content(public_dns, status):
    with pytest.raises(ArticleFetchError, match=str(status)) as caught:
        resolver(Session(response(BODY, status=status))).resolve(GOOGLE)
    assert caught.value.transient is (status in {429, 503})


def test_a_blocked_publisher_is_recorded_as_access_restricted_without_bypass(public_dns):
    publisher_session = Session(response(BODY, status=403))
    wrapped = GoogleNewsArticleFetcher(
        Mock(), enabled=True, resolver=resolver(Session(response(SIGNATURE), rpc_response())),
        publisher=_PublisherFetcher(session=publisher_session, delay=0),
    )
    with pytest.raises(GoogleNewsFetchError, match="access restricted: HTTP 403") as caught:
        wrapped(GOOGLE)
    assert caught.value.google_news == {"status": "access_restricted", "original_url": GOOGLE, "resolved_url": PUBLISHER}
    assert caught.value.transient is False and len(publisher_session.calls) == 1


@pytest.mark.parametrize("html", [
    '<title>Just a moment...</title><article>' + BODY + '</article>',
    '<title>Article</title><script src="/cdn-cgi/challenge-platform/test"></script>' + BODY,
    '<title>404 Not Found</title><article>' + BODY + '</article>',
])
def test_long_challenges_and_error_pages_are_rejected_before_article_parsing(public_dns, html):
    publisher = _PublisherFetcher(session=Session(response(html)), delay=0)
    with pytest.raises(ArticleFetchError):
        publisher(PUBLISHER)


def test_publisher_redirects_are_revalidated_before_a_second_request(public_dns):
    session = Session(response(status=302, Location="http://127.0.0.1/private"))
    with pytest.raises(ArticleFetchError, match="non-public"):
        _PublisherFetcher(session=session, delay=0)(PUBLISHER)
    assert len(session.calls) == 1


def test_safe_transport_pins_the_public_ip_but_keeps_original_tls_hostname(public_dns):
    adapter = _PublicHTTPAdapter()
    adapter.poolmanager = Mock()
    adapter._public_pool(PUBLISHER)
    adapter.poolmanager.connection_from_host.assert_called_once_with(
        "93.184.216.34", port=443, scheme="https",
        pool_kwargs={"server_hostname": "www.techzim.co.zw", "assert_hostname": "www.techzim.co.zw"},
    )
    assert _public_session().trust_env is False


def test_dns_rebinding_is_rejected_before_a_connection_is_opened(monkeypatch):
    replies = iter(["93.184.216.34", "127.0.0.1"])
    def lookup(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(replies), port or 0))]
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    session = _public_session()
    adapter = session.get_adapter(PUBLISHER)
    adapter.poolmanager = Mock()
    with pytest.raises(ArticleFetchError, match="non-public"):
        _PublisherFetcher(session=session, delay=0)(PUBLISHER)
    adapter.poolmanager.connection_from_host.assert_not_called()


def test_google_responses_are_size_capped(public_dns):
    client = GoogleNewsResolver(session=Session(response("x" * 1200)), max_bytes=1000, delay=0)
    with pytest.raises(ArticleFetchError, match="larger than"):
        client.resolve(GOOGLE)


@pytest.mark.parametrize('url', [
    'http://127.0.0.1/private', 'http://[::1]/private', 'http://10.0.0.7/private',
    'http://internal.example/private', 'file:///etc/passwd',
    'https://user:pass@publisher.example/story', 'https://publisher.example:8443/story',
    'https://consent.google.com/continue',
])
def test_unsafe_or_intermediary_destinations_are_rejected(public_dns, url):
    with pytest.raises(ArticleFetchError):
        resolver(Session(response(SIGNATURE), rpc_response(url))).resolve(GOOGLE)


def test_a_publisher_redirect_to_a_private_address_is_never_requested(public_dns):
    session = Session(response(status=302, Location='http://169.254.169.254/latest/meta-data/'))
    with pytest.raises(ArticleFetchError, match='non-public'):
        _PublisherFetcher(session=session, delay=0)(PUBLISHER)
    assert len(session.calls) == 1


def test_a_legitimate_publisher_redirect_uses_the_existing_fetcher(public_dns):
    session = Session(response(status=301, Location='/final-story'), response(article_page('Budget debate', [BODY])))
    article = _PublisherFetcher(session=session, delay=0)(PUBLISHER)
    assert article.url == 'https://www.techzim.co.zw/final-story' and 'budget debate' in article.text
    assert len(session.calls) == 2


@pytest.mark.parametrize('body', ['not JSON', '{}', 'null', '[]', '[["wrb.fr","Fbv4je","not JSON"]]'])
def test_a_changed_or_malformed_google_rpc_fails_closed(public_dns, body):
    with pytest.raises(ArticleFetchError, match='invalid lookup response'):
        resolver(Session(response(SIGNATURE), response(body))).resolve(GOOGLE)


def test_the_google_rpc_does_not_forward_a_post_to_another_host(public_dns):
    session = Session(response(SIGNATURE), response(status=307, Location='https://publisher.example/collect'))
    with pytest.raises(ArticleFetchError, match='unexpected Google News lookup redirect'):
        resolver(session).resolve(GOOGLE)
    assert len(session.calls) == 2
