"""A tiny local HTTP server that serves RSS documents to the real fetch code.

Tests point ``Source.feed_url`` at it, so the existing parser and the HTTP
client run for real - nothing is mocked. All content here is synthetic.
"""

from __future__ import annotations

import threading
from collections import Counter
from email.utils import format_datetime
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape


def rss_document(entries: list[dict], title: str = "Synthetic feed") -> bytes:
    """Build a WordPress-style RSS 2.0 document (full body in content:encoded)."""
    items = []
    for e in entries:
        published = e.get("published", datetime(2026, 11, 3, 9, 0, tzinfo=UTC))
        categories = "".join(f"<category>{escape(c)}</category>" for c in e.get("categories", []))
        guid = f'<guid isPermaLink="false">{escape(e["guid"])}</guid>' if e.get("guid") else ""
        body = e.get("body", f"<p>{e['title']} - synthetic body paragraph.</p>")
        items.append(
            f"<item><title>{escape(e['title'])}</title><link>{escape(e['link'])}</link>"
            f"{guid}<pubDate>{format_datetime(published)}</pubDate>"
            f"<dc:creator>{escape(e.get('author', 'Test Reporter'))}</dc:creator>{categories}"
            f"<description>{escape(e.get('summary', 'Synthetic summary.'))}</description>"
            f"<content:encoded><![CDATA[{body}]]></content:encoded></item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
        f"<title>{escape(title)}</title><link>http://feed.example.test/</link>"
        "<description>Synthetic</description>" + "".join(items) + "</channel></rss>"
    ).encode("utf-8")


class FeedServer:
    """Serves ``routes[path] = (status, body)`` on a random localhost port."""

    def __init__(self) -> None:
        # path -> (status, body, content_type, extra headers)
        self.routes: dict[str, tuple[int, bytes, str, dict[str, str]]] = {}
        self.hits: Counter[str] = Counter()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server API
                owner.hits[self.path] += 1
                status, body, content_type, headers = owner.routes.get(
                    self.path, (404, b"not found", "text/plain", {})
                )
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # keep pytest output clean
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> FeedServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}{path}"

    def serve(
        self,
        path: str,
        body: bytes,
        status: int = 200,
        content_type: str = "application/rss+xml; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> str:
        self.routes[path] = (status, body, content_type, headers or {})
        return self.url(path)

    def serve_html(self, path: str, body: str | bytes, status: int = 200) -> str:
        """Serve an article page."""
        data = body.encode("utf-8") if isinstance(body, str) else body
        return self.serve(path, data, status, content_type="text/html; charset=utf-8")


def article_page(title: str, paragraphs: list[str], *, published: str = "2026-11-03T09:00:00+00:00") -> str:
    """A WordPress-like article page with JSON-LD, Open Graph meta and an entry-content body."""
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        f'<!doctype html><html lang="en"><head><title>{title}</title>'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="article:published_time" content="{published}">'
        '<script type="application/ld+json">'
        f'{{"@type":"NewsArticle","headline":"{title}","datePublished":"{published}",'
        '"author":{"@type":"Person","name":"Test Reporter"}}</script></head>'
        f'<body><nav>Menu Home About</nav><article><h1>{title}</h1>'
        f'<div class="entry-content">{body}</div></article>'
        '<footer>Copyright footer text</footer></body></html>'
    )
