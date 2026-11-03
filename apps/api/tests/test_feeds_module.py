"""The existing RSS fetch/parse code, now importable from the API package.

It used to live only in scripts/check_rss.py. These tests pin that moving it
changed nothing about how it behaves or how it is launched.
"""

import subprocess
import sys

from app.core.config import REPOSITORY_ROOT
from app.ingestion import feeds
from feed_server import rss_document


def test_parser_is_importable_from_the_api_package():
    assert callable(feeds.fetch_rss)
    assert "The Herald" in feeds.RSS_FEEDS
    assert feeds.RSS_FEEDS["The Herald"].startswith("https://")


def test_cli_output_directory_is_still_data_news_in_the_repository_root():
    assert feeds.OUTPUT_DIR == REPOSITORY_ROOT / "data" / "news"


def test_old_script_path_still_launches_the_cli_from_any_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_rss.py"), "--list"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "The Herald" in result.stdout
    assert "Blocked (skipped)" in result.stdout


def test_fetch_rss_parses_a_real_feed_over_http(feed_server):
    url = feed_server.serve("/feed", rss_document([
        {"title": "Kombi overturns on Harare-Mutare road", "guid": "guid-1",
         "link": "https://news.example.test/kombi-overturns/?utm_source=rss&id=7",
         "categories": ["News", "Accidents"], "author": "Jane Reporter"},
        {"title": "Second story", "guid": "guid-2", "link": "https://news.example.test/second/"},
    ]))

    articles, result = feeds.fetch_rss("Synthetic News", url)

    assert result.ok and result.count == 2
    first = articles[0]
    assert first.title == "Kombi overturns on Harare-Mutare road"
    assert first.guid == "guid-1"
    assert first.url == "https://news.example.test/kombi-overturns/?id=7"  # utm_* stripped
    assert first.authors == ["Jane Reporter"]
    assert first.categories == ["News", "Accidents"]
    assert first.published == "2026-11-03T09:00:00+00:00"
    assert "synthetic body paragraph" in first.content_text


def test_fetch_rss_reports_a_failing_feed_instead_of_raising(feed_server):
    url = feed_server.serve("/gone", b"nope", status=404)

    articles, result = feeds.fetch_rss("Broken News", url)

    assert articles == []
    assert not result.ok
    assert "404" in result.error
