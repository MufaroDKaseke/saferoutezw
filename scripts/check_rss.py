#!/usr/bin/env python3
"""Collect full news articles from Zimbabwean sources for SafeRouteZW.

For every article we keep: title, URL, GUID, publish/update times, authors,
categories/tags, summary, the FULL article body (HTML and plain text), images,
language and comment counts. Most sources are read from their WordPress RSS
feeds. Where a feed only carries a short excerpt, the article page itself is
fetched and parsed (JSON-LD, Open Graph meta, article body). Sources without a
usable feed (currently Bulawayo24) are scraped from their homepage HTML.
Sources protected by captcha / Cloudflare challenges are listed in BLOCKED and
are NOT fetched - we do not try to bypass bot protection.

Usage:
    python scripts/check_rss.py                      # fetch all, print summary
    python scripts/check_rss.py --limit 5            # show 5 items per source
    python scripts/check_rss.py --since-hours 24     # only last 24h
    python scripts/check_rss.py --keywords accident crash road kombi
    python scripts/check_rss.py --sources herald newsday
    python scripts/check_rss.py --list               # list configured sources
    python scripts/check_rss.py --no-save            # don't write output files
    python scripts/check_rss.py --no-fetch-pages     # feed data only (fast, excerpts)
    python scripts/check_rss.py --max-pages 5        # cap page fetches per source

Output (unless --no-save): data/news/news_<UTC timestamp>.json (everything,
incl. HTML body) and .csv (flat, without HTML).
Requires: pip install -r scripts/requirements.txt
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
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import mktime
from typing import Any
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

# Where the article body usually lives, most specific first.
BODY_SELECTORS = [
    "[itemprop=articleBody]",
    ".entry-content",
    ".td-post-content",
    ".post-content",
    ".article-content",
    ".article-body",
    ".single-post-content",
    ".story-body",
    "article",
]
NOISE_SELECTORS = (
    "script, style, noscript, iframe, form, nav, aside, footer, button, "
    ".sharedaddy, .share, .social, .related, .related-posts, .comments, "
    "#comments, .newsletter, .advert, .ads, .wp-block-embed"
)
ARTICLE_TYPES = {"newsarticle", "article", "blogposting", "reportagenewsarticle", "opinionnewsarticle"}
# WordPress appends "The post X appeared first on Y." to feed bodies/excerpts
BOILERPLATE = re.compile(r"\s*The post .{0,300}? appeared first on .{0,100}?\.?\s*$", re.S)
# Feed bodies shorter than this (words) are treated as excerpts -> fetch the page
EXCERPT_WORDS = 150


@dataclass
class Article:
    source: str
    title: str
    url: str
    guid: str = ""
    canonical_url: str = ""
    published: str | None = None  # ISO-8601 UTC, None if unknown
    updated: str | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    section: str = ""
    keywords: list[str] = field(default_factory=list)
    summary: str = ""
    content_text: str = ""  # full plain-text body, paragraphs separated by blank lines
    content_html: str = ""  # full body HTML as published
    word_count: int = 0
    image_url: str = ""
    images: list[str] = field(default_factory=list)
    language: str = ""
    comments_count: int | None = None
    comments_url: str = ""
    content_source: str = "none"  # "feed" | "page" | "excerpt" | "none"
    page_error: str = ""
    fetched_at: str = ""


@dataclass
class SourceResult:
    source: str
    method: str  # "rss" | "html"
    ok: bool
    count: int = 0
    seconds: float = 0.0
    error: str = ""
    pages_fetched: int = 0
    pages_failed: int = 0


# --------------------------------------------------------------------------- #
# HTTP + text helpers
# --------------------------------------------------------------------------- #
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


def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _clean_text(raw: str) -> str:
    """HTML fragment -> single-line plain text (titles, summaries)."""
    return _ws(BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True))


def _html_to_text(raw_html: str) -> str:
    """HTML -> plain text, one block (paragraph/heading/list item) per paragraph."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for bad in soup.select(NOISE_SELECTORS):
        bad.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    blocks = [
        _ws(el.get_text(" ", strip=True))
        for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"])
        if not el.find(["p", "li", "blockquote"])  # innermost blocks only
    ]
    blocks = [b for b in blocks if b]
    text = "\n\n".join(blocks)
    # markup without <p> (text separated by <br>/<div>): fall back to line-based text
    whole = "\n\n".join(_ws(ln) for ln in soup.get_text("\n").split("\n") if _ws(ln))
    if len(whole.split()) > max(len(text.split()) * 1.5, 40):
        text = whole
    return BOILERPLATE.sub("", text).strip()


def _strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _iso(value: Any) -> str | None:
    """struct_time or ISO date string -> ISO-8601 UTC string (None if unparseable)."""
    if not value:
        return None
    try:
        if isinstance(value, time.struct_time):
            return datetime.fromtimestamp(mktime(value), tz=timezone.utc).isoformat()
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _images_in(fragment: str, base: str = "") -> list[str]:
    soup = BeautifulSoup(fragment or "", "html.parser")
    out = []
    for img in soup.find_all("img"):
        src = str(img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "")
        if src and not src.startswith("data:"):
            out.append(urljoin(base, src))
    return out


def _uniq(items) -> list[str]:
    seen, out = set(), []
    for i in items:
        i = (i or "").strip()
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _names(value: Any) -> list[str]:
    return _uniq(v.get("name", "") if isinstance(v, dict) else str(v) for v in _as_list(value))


def _image_urls(value: Any) -> list[str]:
    return _uniq(v.get("url", "") if isinstance(v, dict) else str(v) for v in _as_list(value))


# --------------------------------------------------------------------------- #
# Article-page extraction
# --------------------------------------------------------------------------- #
def _jsonld_article(soup: BeautifulSoup) -> dict:
    """First schema.org Article-like object in the page's JSON-LD, if any."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        stack = _as_list(data)
        while stack:
            node = stack.pop(0)
            if not isinstance(node, dict):
                continue
            stack.extend(_as_list(node.get("@graph")))
            types = {str(t).lower() for t in _as_list(node.get("@type"))}
            if types & ARTICLE_TYPES:
                return node
    return {}


def extract_page(page_html: str, url: str) -> dict:
    """Pull structured article data out of a full article page."""
    soup = BeautifulSoup(page_html, "html.parser")
    ld = _jsonld_article(soup)

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return _ws(str(tag["content"]))
        return ""

    body_el = None
    for sel in BODY_SELECTORS:
        for el in soup.select(sel):
            if len(el.get_text(strip=True)) >= 200:
                body_el = el
                break
        if body_el:
            break

    if body_el is None:  # unknown layout: container holding the most paragraph text
        best_len = 0
        for el in soup.find_all(["div", "section", "main"]):
            n = sum(len(p.get_text(strip=True)) for p in el.find_all("p", recursive=False))
            if n > best_len:
                body_el, best_len = el, n
        if best_len < 200:
            body_el = None

    body_html = body_text = ""
    if body_el is not None:
        for bad in body_el.select(NOISE_SELECTORS):
            bad.decompose()
        body_html = str(body_el)
        body_text = _html_to_text(body_html)
    if len(body_text) < 200 and ld.get("articleBody"):
        body_text = _html_to_text(str(ld["articleBody"]))

    tags = [t.get("content", "") for t in soup.find_all("meta", attrs={"property": "article:tag"})]
    keywords = ld.get("keywords") or meta("news_keywords", "keywords")
    if isinstance(keywords, str):
        keywords = re.split(r"\s*,\s*", keywords)
    html_tag = soup.find("html")
    canonical = soup.find("link", rel="canonical")

    images = [*_image_urls(ld.get("image")), meta("og:image"), *_images_in(body_html, url)]
    return {
        "canonical_url": canonical["href"] if canonical and canonical.get("href") else meta("og:url"),
        "title": _ws(str(ld.get("headline") or "")) or meta("og:title"),
        "published": _iso(ld.get("datePublished")) or _iso(meta("article:published_time")),
        "updated": _iso(ld.get("dateModified")) or _iso(meta("article:modified_time")),
        "authors": _names(ld.get("author")) or _uniq([meta("author", "article:author", "og:article:author")]),
        "section": _ws(" / ".join(_names(ld.get("articleSection")))) or meta("article:section", "og:article:section"),
        "keywords": _uniq([*(keywords or []), *tags]),
        "summary": _ws(str(ld.get("description") or "")) or meta("og:description", "description"),
        "language": (html_tag.get("lang", "") if html_tag else "") or meta("og:locale"),
        "images": _uniq(images),
        "content_text": body_text,
        "content_html": body_html,
    }


def _merge_page(a: Article, page: dict) -> None:
    """Fill gaps from the page; replace the body only if the page has clearly more."""
    for key in ("canonical_url", "published", "updated", "section", "language", "summary"):
        if not getattr(a, key) and page.get(key):
            setattr(a, key, page[key])
    a.authors = a.authors or page.get("authors", [])
    a.keywords = _uniq([*a.keywords, *page.get("keywords", [])])
    a.images = _uniq([*a.images, *page.get("images", [])])
    a.image_url = a.image_url or (a.images[0] if a.images else "")
    page_words = len(page["content_text"].split())
    if page_words > max(a.word_count * 1.2, 40):
        a.content_text, a.content_html = page["content_text"], page["content_html"]
        a.word_count, a.content_source = page_words, "page"


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
def fetch_rss(name: str, url: str) -> tuple[list[Article], SourceResult]:
    start = time.time()
    try:
        resp = _get(_session(), url)
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            raise ValueError("feed returned no entries (not RSS, or empty)")
        now = datetime.now(timezone.utc).isoformat()
        articles = []
        for e in feed.entries:
            if not e.get("link"):
                continue
            full_html = "\n".join(c.get("value", "") for c in e.get("content", []))
            excerpt = BOILERPLATE.sub("", _clean_text(e.get("summary", ""))).strip()
            text = _html_to_text(full_html) if full_html else ""
            source_kind = "feed" if text else ("excerpt" if excerpt else "none")
            text = text or excerpt  # excerpt-only feeds: placeholder until page is fetched

            images = [m.get("url", "") for m in [*e.get("media_content", []), *e.get("media_thumbnail", [])]]
            images += [x.get("href", "") for x in e.get("enclosures", []) if "image" in x.get("type", "image")]
            images += _images_in(full_html or e.get("summary", ""), e["link"])
            images = _uniq(images)
            comments = str(e.get("slash_comments", ""))
            authors = [a.get("name", "") for a in e.get("authors", [])] or [e.get("author", "")]

            articles.append(
                Article(
                    source=name,
                    title=_clean_text(e.get("title", "Untitled")),
                    url=_strip_tracking(e["link"]),
                    guid=e.get("id", ""),
                    published=_iso(e.get("published_parsed") or e.get("updated_parsed")),
                    updated=_iso(e.get("updated_parsed")) if e.get("published_parsed") else None,
                    authors=_uniq(authors),
                    categories=_uniq(t.get("term", "") for t in e.get("tags", [])),
                    summary=excerpt,
                    content_text=text,
                    content_html=full_html,
                    word_count=len(text.split()),
                    image_url=images[0] if images else "",
                    images=images,
                    language=e.get("language", "") or feed.feed.get("language", ""),
                    comments_count=int(comments) if comments.isdigit() else None,
                    comments_url=e.get("comments", ""),
                    content_source=source_kind,
                    fetched_at=now,
                )
            )
        return articles, SourceResult(name, "rss", True, len(articles), time.time() - start)
    except Exception as exc:  # noqa: BLE001 - report any failure per source
        return [], SourceResult(name, "rss", False, 0, time.time() - start, str(exc)[:200])


# Bulawayo24 article links look like: index-id-news-sc-national-byo-267820.html
_B24_LINK = re.compile(r"index-id-news-[\w-]*?-(\d+)\.html")
_B24_DATE = re.compile(r"(\d{1,2} \w{3} \d{4} at \d{1,2}:\d{2})\s*hrs(?:\s*\|\s*\d+)?\s*$")


_B24_AGO = re.compile(r"(\d+)\s*(min|hr|day)s?\s*ago(?:\s*\|\s*\d+)?\s*$", re.I)
_B24_UNITS = {"min": 1, "hr": 60, "day": 1440}  # minutes per unit


def _scrape_bulawayo24(soup: BeautifulSoup, base: str, name: str) -> list[Article]:
    best: dict[str, Article] = {}
    now = datetime.now(timezone.utc).isoformat()
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
        rm = _B24_AGO.search(title)  # recent items: "Headline 8 hrs ago | 339"
        if rm:
            title = title[: rm.start()].strip()
            unit = _B24_UNITS[rm.group(2).lower()]
            published = (datetime.now(timezone.utc) - timedelta(minutes=int(rm.group(1)) * unit)).isoformat()
        if len(title) < 15:
            continue
        link = urljoin(base, a["href"])
        prev = best.get(link)
        if prev is None:
            best[link] = Article(
                source=name, title=title, url=link, guid=m.group(1), published=published, fetched_at=now
            )
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


def enrich_with_pages(articles: list[Article], max_pages: int, delay: float, res: SourceResult) -> None:
    """Fetch article pages for items whose feed body is only an excerpt.

    Runs sequentially per source with a small delay so no site is hammered.
    """
    session = _session()
    todo = [a for a in articles if a.word_count < EXCERPT_WORDS][:max_pages]
    for a in todo:
        try:
            _merge_page(a, extract_page(_get(session, a.url).text, a.url))
            res.pages_fetched += 1
        except Exception as exc:  # noqa: BLE001
            a.page_error = str(exc)[:150]
            res.pages_failed += 1
        time.sleep(delay)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _matches(name: str, selected: set[str] | None) -> bool:
    """No filter = all; otherwise case-insensitive substring match."""
    return not selected or any(sel in name.lower() for sel in selected)


def collect(
    selected: set[str] | None,
    workers: int = 8,
    fetch_pages: bool = True,
    max_pages: int = 30,
    delay: float = 0.4,
    since_hours: float | None = None,
):
    jobs = []
    for name, url in RSS_FEEDS.items():
        if _matches(name, selected):
            jobs.append((fetch_rss, name, url))
    for name, url in HTML_SOURCES.items():
        if _matches(name, selected):
            jobs.append((fetch_html, name, url))

    def run(job):
        fn, name, url = job
        arts, res = fn(name, url)
        if fetch_pages and arts:
            # only spend page fetches on items that will survive the date filter
            enrich_with_pages(filter_articles(arts, since_hours, None), max_pages, delay, res)
        return arts, res

    articles: list[Article] = []
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for arts, res in pool.map(run, jobs):
            articles.extend(arts)
            results.append(res)
    return articles, results


def dedupe(articles: list[Article]) -> list[Article]:
    best: dict[str, Article] = {}
    for a in articles:
        key = a.url.split("#")[0].rstrip("/").lower()
        if key not in best or a.word_count > best[key].word_count:
            best[key] = a
    return list(best.values())


def filter_articles(
    articles: list[Article], since_hours: float | None, keywords: list[str] | None
) -> list[Article]:
    out = articles
    if since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        # undated items are kept: we can't tell their age
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
            if any(
                k in f"{a.title} {a.summary} {a.content_text} {' '.join(a.categories + a.keywords)}".lower()
                for k in kws
            )
        ]
    return out


CSV_SKIP = {"content_html", "images"}  # HTML / image lists live in the JSON file only


def save(articles: list[Article]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUTPUT_DIR / f"news_{stamp}.json"
    csv_path = OUTPUT_DIR / f"news_{stamp}.csv"
    rows = [asdict(a) for a in articles]
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    cols = [f.name for f in fields(Article) if f.name not in CSV_SKIP]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in r.items()})
    return json_path, csv_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=3, help="items to print per source (default 3)")
    p.add_argument("--since-hours", type=float, help="only keep items newer than N hours")
    p.add_argument("--keywords", nargs="+", help="keep items matching any keyword (searches full text)")
    p.add_argument("--sources", nargs="+", help="only these sources (names as in --list)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--no-fetch-pages", action="store_true", help="feed data only; skip article pages")
    p.add_argument("--max-pages", type=int, default=30, help="max article pages fetched per source")
    p.add_argument("--delay", type=float, default=0.4, help="seconds between page fetches per source")
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

    articles, results = collect(
        selected,
        args.workers,
        fetch_pages=not args.no_fetch_pages,
        max_pages=args.max_pages,
        delay=args.delay,
        since_hours=args.since_hours,
    )
    total_raw = len(articles)
    articles = filter_articles(dedupe(articles), args.since_hours, args.keywords)
    articles.sort(key=lambda a: a.published or "", reverse=True)

    print(f"{'Source':<20} {'Via':<5} {'Status':<7} {'Items':>5} {'Pages':>6}  Note")
    for r in sorted(results, key=lambda r: r.source):
        pages = f"{r.pages_fetched}/{r.pages_fetched + r.pages_failed}"
        print(f"{r.source:<20} {r.method:<5} {'OK' if r.ok else 'FAIL':<7} {r.count:>5} {pages:>6}  {r.error}")

    by_source: dict[str, list[Article]] = {}
    for a in articles:
        by_source.setdefault(a.source, []).append(a)
    for src in sorted(by_source):
        print(f"\n{src} ({len(by_source[src])} kept)")
        for a in by_source[src][: args.limit]:
            by = ", ".join(a.authors) or "unknown author"
            print(f" - {a.title}")
            print(f"   {a.published or 'no date'} | {by} | {a.word_count} words | body: {a.content_source}")
            print(f"   {a.url}")

    ok = sum(r.ok for r in results)
    print(f"\n{ok}/{len(results)} sources ok | {total_raw} fetched | {len(articles)} after dedupe/filters")
    print(f"Skipped (blocked): {', '.join(BLOCKED)}")

    if not args.no_save and articles:
        jp, cp = save(articles)
        print(f"Saved: {jp}\n       {cp}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
