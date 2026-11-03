#!/usr/bin/env python3
"""Collect headlines from Zimbabwean news sources for SafeRouteZW.

Most sources are fetched from their WordPress RSS feeds. Sources without a
usable feed (currently Bulawayo24) are scraped from their homepage HTML.
Sources protected by captcha / Cloudflare challenges are listed in BLOCKED and
are NOT fetched - we do not try to bypass bot protection.

Usage:
    python scripts/check_rss.py                      # fetch all, print summary
    python scripts/check_rss.py --limit 5            # show 5 items per source
    python scripts/check_rss.py --since-hours 24     # only last 24h
    python scripts/check_rss.py --keywords accident crash road kombi
    python scripts/check_rss.py --sources Herald NewsDay
    python scripts/check_rss.py --list               # list configured sources
    python scripts/check_rss.py --no-save            # don't write output files

Output (unless --no-save): data/news/news_<UTC timestamp>.json and .csv
Requires: pip install feedparser requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import mktime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; SafeRouteZW/0.1; +news research; "
    "respects robots/captcha)"
)
TIMEOUT = 20
RETRIES = 2
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "news"

# name -> RSS/Atom feed URL (verified working 2026-11-03)
RSS_FEEDS: dict[str, str] = {
    "The Herald": "https://www.herald.co.zw/feed/",
    "NewsDay": "https://www.newsday.co.zw/feed/",
    "Techzim": "https://www.techzim.co.zw/feed/",
    "Pindula News": "https://news.pindula.co.zw/feed/",
    "263Chat": "https://www.263chat.com/feed/",
    "Zimbabwe Situation": "https://www.zimbabwesituation.com/feed/",
    "ZimEye": "https://www.zimeye.net/feed/",
    "Zim Morning Post": "https://zimmorningpost.com/feed/",
    "Daily News": "https://dailynews.co.zw/feed/",
    "The Standard": "https://www.thestandard.co.zw/feed/",
    "The Independent": "https://www.theindependent.co.zw/feed/",
    "The Zimbabwe Mail": "https://www.thezimbabwemail.com/feed/",
    "CITE": "https://cite.org.zw/feed/",
    "The NewsHawks": "https://thenewshawks.com/feed/",
    "Open Parly": "https://openparly.com/feed/",
    "Nehanda Radio": "https://nehandaradio.com/feed/",
    "ZBC News": "https://www.zbcnews.co.zw/feed/",
    "MyZimbabwe": "https://www.myzimbabwe.co.zw/feed/",
    "iHarare": "https://iharare.com/feed/",
    "Masvingo Mirror": "https://masvingomirror.com/feed/",
    "Business Weekly": "https://www.businessweekly.co.zw/feed/",
    "Financial Gazette": "https://fingaz.co.zw/feed/",
}

# name -> homepage URL scraped for article links (no usable RSS feed)
HTML_SOURCES: dict[str, str] = {
    "Bulawayo24": "https://bulawayo24.com/",
}

# Reachable only through captcha / Cloudflare challenges, or serve empty feeds.
# Skipped on purpose; re-check occasionally or use an official API/permission.
BLOCKED: dict[str, str] = {
    "NewZimbabwe": "captcha challenge (sgcaptcha)",
    "ZimLive": "Cloudflare challenge (403)",
    "HarareLive": "captcha challenge (sgcaptcha)",
    "Chronicle": "empty feed + Cloudflare 403 on site",
    "Manica Post": "empty feed + Cloudflare 403 on site",
    "Sunday Mail / Sunday News": "empty feeds; content mirrors The Herald",
}


@dataclass
class Article:
    source: str
    title: str
    url: str
    published: str | None = None  # ISO-8601 UTC, None if unknown
    summary: str = ""
    categories: list[str] = field(default_factory=list)


@dataclass
class SourceResult:
    source: str
    method: str  # "rss" | "html"
    ok: bool
    count: int = 0
    seconds: float = 0.0
    error: str = ""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/xml,text/xml,text/html,*/*",
        }
    )
    return s


def _get(session: requests.Session, url: str) -> requests.Response:
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last = exc
            # 4xx (other than 429) won't get better by retrying
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                break
            time.sleep(1.5 * (attempt + 1))
    assert last is not None
    raise last


def _clean_text(raw: str, max_len: int = 400) -> str:
    text = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", html.unescape(text))
    return text[:max_len]


def _strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _entry_date(entry) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc).isoformat()


def fetch_rss(name: str, url: str) -> tuple[list[Article], SourceResult]:
    start = time.time()
    try:
        resp = _get(_session(), url)
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            raise ValueError("feed returned no entries (not RSS, or empty)")
        articles = [
            Article(
                source=name,
                title=_clean_text(e.get("title", "Untitled"), 300),
                url=_strip_tracking(e.get("link", "")),
                published=_entry_date(e),
                summary=_clean_text(e.get("summary", "")),
                categories=[t.get("term", "") for t in e.get("tags", []) if t.get("term")],
            )
            for e in feed.entries
            if e.get("link")
        ]
        return articles, SourceResult(name, "rss", True, len(articles), time.time() - start)
    except Exception as exc:  # noqa: BLE001 - report any failure per source
        return [], SourceResult(name, "rss", False, 0, time.time() - start, str(exc)[:200])


# Bulawayo24 article links look like: index-id-news-sc-national-byo-267820.html
_B24_LINK = re.compile(r"index-id-news-[\w-]*?-(\d+)\.html")
_B24_DATE = re.compile(r"(\d{1,2} \w{3} \d{4} at \d{1,2}:\d{2})\s*hrs(?:\s*\|\s*\d+)?\s*$")


def _scrape_bulawayo24(soup: BeautifulSoup, base: str, name: str) -> list[Article]:
    best: dict[str, Article] = {}
    for a in soup.find_all("a", href=True):
        m = _B24_LINK.search(a["href"])
        if not m or "#" in a["href"]:
            continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(title) < 15:  # skips "News", "Join the discussion", etc.
            continue
        # titles look like "Headline 01 Nov 2026 at 18:27hrs | 823" (date | views)
        published = None
        dm = _B24_DATE.search(title)
        if dm:
            title = title[: dm.start()].strip()
            try:
                # site shows Zimbabwe time (CAT, UTC+2)
                local = datetime.strptime(dm.group(1), "%d %b %Y at %H:%M")
                published = (local - timedelta(hours=2)).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
        if len(title) < 15:
            continue
        link = urljoin(base, a["href"])
        prev = best.get(link)
        if prev is None:
            best[link] = Article(source=name, title=title, url=link, published=published)
        else:  # same article linked several times: merge the best title + any date
            prev.published = prev.published or published
            if len(title) > len(prev.title):
                prev.title = title
    return list(best.values())


HTML_SCRAPERS = {"Bulawayo24": _scrape_bulawayo24}


def fetch_html(name: str, url: str) -> tuple[list[Article], SourceResult]:
    start = time.time()
    try:
        resp = _get(_session(), url)
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = HTML_SCRAPERS[name](soup, url, name)
        if not articles:
            raise ValueError("no articles found - page layout may have changed")
        return articles, SourceResult(name, "html", True, len(articles), time.time() - start)
    except Exception as exc:  # noqa: BLE001
        return [], SourceResult(name, "html", False, 0, time.time() - start, str(exc)[:200])


def _matches(name: str, selected: set[str] | None) -> bool:
    """No filter = all; otherwise case-insensitive substring match."""
    return not selected or any(sel in name.lower() for sel in selected)


def collect(selected: set[str] | None, workers: int = 8):
    jobs = []
    for name, url in RSS_FEEDS.items():
        if _matches(name, selected):
            jobs.append((fetch_rss, name, url))
    for name, url in HTML_SOURCES.items():
        if _matches(name, selected):
            jobs.append((fetch_html, name, url))

    articles: list[Article] = []
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for arts, res in pool.map(lambda j: j[0](j[1], j[2]), jobs):
            articles.extend(arts)
            results.append(res)
    return articles, results


def dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    out = []
    for a in articles:
        key = a.url.split("#")[0].rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def filter_articles(
    articles: list[Article], since_hours: float | None, keywords: list[str] | None
) -> list[Article]:
    out = articles
    if since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        # undated items (HTML sources) are kept: we can't tell their age
        out = [
            a
            for a in out
            if a.published is None or datetime.fromisoformat(a.published) >= cutoff
        ]
    if keywords:
        kws = [k.lower() for k in keywords]
        out = [
            a
            for a in out
            if any(k in f"{a.title} {a.summary} {' '.join(a.categories)}".lower() for k in kws)
        ]
    return out


def save(articles: list[Article]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUTPUT_DIR / f"news_{stamp}.json"
    csv_path = OUTPUT_DIR / f"news_{stamp}.csv"
    rows = [asdict(a) for a in articles]
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f, fieldnames=["source", "title", "url", "published", "summary", "categories"]
        )
        w.writeheader()
        for r in rows:
            r["categories"] = "; ".join(r["categories"])
            w.writerow(r)
    return json_path, csv_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=3, help="items to print per source (default 3)")
    p.add_argument("--since-hours", type=float, help="only keep items newer than N hours")
    p.add_argument("--keywords", nargs="+", help="keep items matching any keyword")
    p.add_argument("--sources", nargs="+", help="only these sources (names as in --list)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--no-save", action="store_true", help="don't write JSON/CSV output")
    p.add_argument("--list", action="store_true", help="list sources and exit")
    args = p.parse_args()

    if args.list:
        print("RSS:", *sorted(RSS_FEEDS), sep="\n  ")
        print("HTML:", *sorted(HTML_SOURCES), sep="\n  ")
        print("Blocked (skipped):", *[f"{k} - {v}" for k, v in BLOCKED.items()], sep="\n  ")
        return 0

    selected = {s.lower() for s in args.sources} if args.sources else None
    all_names = {n.lower() for n in [*RSS_FEEDS, *HTML_SOURCES]}
    if selected and (unknown := {s for s in selected if not any(s in n for n in all_names)}):
        print(f"Unknown source(s): {', '.join(sorted(unknown))}. Use --list.", file=sys.stderr)
        return 2

    articles, results = collect(selected, args.workers)
    total_raw = len(articles)
    articles = filter_articles(dedupe(articles), args.since_hours, args.keywords)
    articles.sort(key=lambda a: a.published or "", reverse=True)

    print(f"{'Source':<20} {'Via':<5} {'Status':<7} {'Items':>5}  Note")
    for r in sorted(results, key=lambda r: r.source):
        print(f"{r.source:<20} {r.method:<5} {'OK' if r.ok else 'FAIL':<7} {r.count:>5}  {r.error}")

    by_source: dict[str, list[Article]] = {}
    for a in articles:
        by_source.setdefault(a.source, []).append(a)
    for src in sorted(by_source):
        print(f"\n{src} ({len(by_source[src])} kept)")
        for a in by_source[src][: args.limit]:
            print(f" - {a.title}\n   {a.url}")

    ok = sum(r.ok for r in results)
    print(f"\n{ok}/{len(results)} sources ok | {total_raw} fetched | {len(articles)} after dedupe/filters")
    print(f"Skipped (blocked): {', '.join(BLOCKED)}")

    if not args.no_save and articles:
        jp, cp = save(articles)
        print(f"Saved: {jp}\n       {cp}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
