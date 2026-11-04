"""Facebook Pages through ``neverempty/facebook-page-posts-scraper``.

Actor contract, taken from the published input schema and README (build 0.1.13), not guessed:

* input ``startUrls`` (list of Page addresses), ``resultsLimit`` (posts per Page, newest first),
  ``onlyPostsNewerThan`` ("24 hours", "7 days", a date), ``maxItems`` (total cap);
* output rows ``dataType: "post"`` with ``postId``, ``url``, ``time`` (ISO), ``timestamp``,
  ``text`` (null for media-only posts), ``link`` (external URL), ``sharedPostUrl``, ``pageId``,
  ``pageUrl``, ``pageName``, ``coAuthors``; plus free ``dataType: "note"`` rows with
  ``reason`` / ``message`` explaining why a Page returned nothing;
* ``facebookUrl`` is the address we *asked for*, so it proves nothing about who wrote the post.
  Origin is judged only from ``pageId`` / ``pageUrl``.

Nothing here reads comments, followers or other profiles: the Actor is asked for one Page's
posts and the engagement numbers it also returns are ignored and never stored.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.ingestion.normalized import SOCIAL_POST, NormalizedReport, make_title
from app.ingestion.rss import canonicalize_url
from app.ingestion.social.base import (
    ACCEPT,
    IGNORE,
    QUARANTINE,
    REJECT,
    Notice,
    SocialSourceRef,
    Verdict,
)

PLATFORM = "facebook"
FACEBOOK_HOSTS = ("facebook.com", "fb.com", "fb.watch")
# Links that stay inside Facebook's family are not "an external article".
INTERNAL_LINK_HOSTS = FACEBOOK_HOSTS + ("fb.me", "instagram.com", "messenger.com", "l.facebook.com", "whatsapp.com", "wa.me")
# First path segments that are Facebook routes, not account names.
RESERVED_SEGMENTS = frozenset(
    {
        "permalink.php", "story.php", "photo.php", "photo", "photos", "watch", "reel", "reels", "share",
        "videos", "video.php", "groups", "events", "hashtag", "l.php", "login", "marketplace", "stories",
        "pg", "public", "plugins", "dialog", "sharer", "sharer.php", "profile.php", "people", "pages",
    }
)
BLOCKING_MARKERS = ("not-found", "not_found", "blocked", "refus", "private", "invalid", "unsupported", "login")
FUTURE_TOLERANCE = timedelta(days=1)


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #
def _is_host(host: str, domains: tuple[str, ...]) -> bool:
    host = host.lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


def is_facebook_url(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url.strip())
    return parts.scheme in ("http", "https") and _is_host(parts.netloc, FACEBOOK_HOSTS)


def account_key(url: str | None) -> str | None:
    """Stable identity of a Page address: ``name:<handle>`` or ``id:<numeric id>``; None if opaque."""
    if not url:
        return None
    raw = url.strip()
    parts = urlsplit(raw if "://" in raw else "https://www.facebook.com/" + raw.lstrip("@/"))
    if not _is_host(parts.netloc, FACEBOOK_HOSTS):
        return None
    segments = [s for s in parts.path.split("/") if s]
    if not segments:
        return None
    first = segments[0].lower()
    if first == "profile.php":
        values = parse_qs(parts.query).get("id")
        return f"id:{values[0]}" if values and values[0].isdigit() else None
    if first in ("people", "pages") and len(segments) >= 3 and segments[-1].isdigit():
        return f"id:{segments[-1]}"
    if first in RESERVED_SEGMENTS:
        return None
    if first.isdigit():  # facebook.com/<numeric id> is the Page's id, not a vanity name
        return f"id:{first}"
    return f"name:{first}"


def post_owner_key(url: str) -> str | None:
    """Whose Page a post URL belongs to, when the URL says (``/<page>/posts/<id>``, ``permalink.php?id=``)."""
    parts = urlsplit(url.strip())
    segments = [s for s in parts.path.split("/") if s]
    if segments and segments[0].lower() in ("permalink.php", "story.php"):
        values = parse_qs(parts.query).get("id")
        return f"id:{values[0]}" if values and values[0].isdigit() else None
    return account_key(url)


def canonical_account_url(url: str) -> str:
    """The form stored for an account: https, no tracking, no trailing slash, host lower-cased."""
    return canonicalize_url(url)


def _compare(a: str, b: str) -> bool | None:
    """True/False when both keys are of the same kind; None when they cannot be compared."""
    if a.split(":", 1)[0] != b.split(":", 1)[0]:
        return None
    return a == b


def _configured_keys(source: SocialSourceRef) -> set[str]:
    keys = {account_key(source.account_url)}
    if source.platform_account_id:
        keys.add(f"id:{source.platform_account_id}")
    return {k for k in keys if k}


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #
def _parse_time(item: dict[str, Any]) -> datetime | None:
    value = item.get("time")
    parsed: datetime | None = None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None and isinstance(item.get("timestamp"), (int, float)):
        try:
            parsed = datetime.fromtimestamp(float(item["timestamp"]), tz=UTC)
        except (OverflowError, OSError, ValueError):
            parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed > datetime.now(UTC) + FUTURE_TOLERANCE:
        return None  # an impossible date is worse than none
    return parsed


def _external_link(item: dict[str, Any]) -> str | None:
    link = item.get("link")
    if not isinstance(link, str) or not link.strip():
        return None
    parts = urlsplit(link.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc or _is_host(parts.netloc, INTERNAL_LINK_HOSTS):
        return None
    return link.strip()


class FacebookAdapter:
    platform = PLATFORM

    def max_items(self, source: SocialSourceRef) -> int:
        return source.max_posts_per_run

    def build_input(self, source: SocialSourceRef, *, since_hours: int) -> dict[str, Any]:
        return {
            "startUrls": [source.account_url],  # exactly one allow-listed Page per run
            "resultsLimit": source.max_posts_per_run,
            "onlyPostsNewerThan": f"{since_hours} hours",
            "maxItems": self.max_items(source),
        }

    def notice(self, item: dict[str, Any]) -> Notice | None:
        if item.get("dataType") != "note":
            return None
        reason = str(item.get("reason") or "note")[:64]
        message = str(item.get("message") or "")[:300]
        blocking = any(marker in reason.lower() for marker in BLOCKING_MARKERS)
        return Notice(reason=reason, message=message, blocking=blocking)

    def judge(self, item: dict[str, Any], source: SocialSourceRef, *, max_chars: int) -> Verdict:
        if not source.enabled:
            return Verdict(REJECT, "source_disabled")

        post_id = str(item.get("postId") or "").strip()
        url = item.get("url") if isinstance(item.get("url"), str) else ""
        url = url.strip()
        page_id = str(item.get("pageId") or "").strip() or None
        page_url = item.get("pageUrl") if isinstance(item.get("pageUrl"), str) else None
        detail = {
            "claimed_page_id": page_id,
            "claimed_page_url": (page_url or "")[:300] or None,
            "claimed_page_name": str(item.get("pageName") or "")[:120] or None,
        }
        identity = {"external_id": post_id or None, "post_url": url[:500] or None, "detail": detail}

        if not post_id or not url:
            return Verdict(QUARANTINE, "missing_post_identity", **identity)
        if not is_facebook_url(url):
            return Verdict(QUARANTINE, "post_url_not_facebook", **identity)
        if "/groups/" in urlsplit(url).path:
            return Verdict(REJECT, "group_post", **identity)

        # 1. Who published it? Only pageId / pageUrl count (facebookUrl is our own input echoed back).
        configured = _configured_keys(source)
        configured_id = source.platform_account_id
        verdict: bool | None = None
        learned: str | None = None
        if configured_id and page_id:
            verdict = page_id == configured_id
        if verdict is None:
            post_key = account_key(page_url)
            results = [_compare(post_key, key) for key in configured] if post_key else []
            if True in results:
                verdict = True
                if page_id and not configured_id:
                    learned = page_id  # URL matched the configured Page: pin its numeric id
            elif False in results:
                verdict = False
        if verdict is False:
            return Verdict(REJECT, "origin_mismatch", **identity)
        if verdict is None:
            return Verdict(QUARANTINE, "origin_unverifiable", **identity)

        # 2. Does the post's own URL belong to that account?
        owner = post_owner_key(url)
        if owner is not None:
            owner_results = [_compare(owner, key) for key in configured]
            if False in owner_results and True not in owner_results:
                return Verdict(QUARANTINE, "post_url_other_account", **identity)

        # 3. Is there anything to read?
        text = str(item.get("text") or "").strip()
        if not text:
            return Verdict(IGNORE, "no_text", **identity)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"

        shared = item.get("sharedPostUrl") if isinstance(item.get("sharedPostUrl"), str) else None
        report = NormalizedReport(
            external_id=f"facebook:{post_id}",
            url=url,
            text=text,
            title=make_title(text),
            published_at=_parse_time(item),
            content_kind=SOCIAL_POST,
            linked_article_url=_external_link(item),
            extra={
                "platform": PLATFORM,
                "post_id": post_id,
                "account_url": source.account_url,
                "page_name": detail["claimed_page_name"],
                # A reshare is recorded but never followed into the original poster's account.
                "shared_post_url": shared[:500] if shared else None,
                "has_co_authors": bool(item.get("coAuthors")),
            },
        )
        return Verdict(ACCEPT, report=report, learned_account_id=learned, **identity)
