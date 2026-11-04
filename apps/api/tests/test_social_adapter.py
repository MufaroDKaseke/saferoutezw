"""Facebook adapter rules: allowlist, origin validation, normalisation. Pure functions; no database.

All accounts, ids and text are synthetic.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.ingestion.social.base import ACCEPT, IGNORE, QUARANTINE, REJECT, SocialSourceRef
from app.ingestion.social.facebook import (
    FacebookAdapter,
    account_key,
    is_facebook_url,
    post_owner_key,
)
from app.ingestion.social.poller import is_due, since_hours

ADAPTER = FacebookAdapter()
PAGE = "https://www.facebook.com/roadwatchzw"


def source(**overrides) -> SocialSourceRef:
    values = dict(
        source_id=uuid.uuid4(), name="Road Watch", platform="facebook", account_url=PAGE,
        platform_account_id=None, actor_id="neverempty/facebook-page-posts-scraper", enabled=True,
        poll_interval_seconds=7200, max_posts_per_run=10, last_polled_at=None, last_success_at=None,
        last_post_id=None, last_post_at=None, collection_status="idle",
    )
    values.update(overrides)
    return SocialSourceRef(**values)


def post(**overrides) -> dict:
    item = {
        "dataType": "post", "facebookUrl": PAGE, "postId": "9001",
        "url": f"{PAGE}/posts/9001", "time": "2026-11-03T08:00:00.000Z",
        "text": "Kombi overturned near Rusape, five injured.", "pageId": "555", "pageUrl": PAGE,
        "pageName": "Road Watch", "likes": 12, "comments": 3,
    }
    item.update(overrides)
    return item


def judge(item, src=None):
    return ADAPTER.judge(item, src or source(), max_chars=8000)


# -- URL identity ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://www.facebook.com/RoadWatchZW/", "name:roadwatchzw"),
        ("https://m.facebook.com/roadwatchzw?ref=x", "name:roadwatchzw"),
        ("roadwatchzw", "name:roadwatchzw"),
        ("@roadwatchzw", "name:roadwatchzw"),
        ("https://www.facebook.com/profile.php?id=100123", "id:100123"),
        ("https://www.facebook.com/61572906399484", "id:61572906399484"),
        ("https://www.facebook.com/people/Road-Watch/100123/", "id:100123"),
        ("https://www.facebook.com/groups/abc", None),
        ("https://www.facebook.com/permalink.php?story_fbid=1&id=5", None),
        ("https://evil.example.com/roadwatchzw", None),
        ("", None),
    ],
)
def test_account_key(url, key):
    assert account_key(url) == key


def test_post_owner_key_reads_permalink_ids_and_handles():
    assert post_owner_key("https://www.facebook.com/permalink.php?story_fbid=1&id=555") == "id:555"
    assert post_owner_key(f"{PAGE}/posts/9001") == "name:roadwatchzw"
    assert post_owner_key("https://www.facebook.com/share/p/abc") is None


def test_only_facebook_hosts_are_facebook_urls():
    assert is_facebook_url("https://www.facebook.com/x/posts/1")
    assert is_facebook_url("https://fb.watch/abc")
    assert not is_facebook_url("https://facebook.com.evil.test/x")
    assert not is_facebook_url("javascript:alert(1)")


# -- Actor request ---------------------------------------------------------------
def test_actor_input_targets_exactly_one_allow_listed_page():
    run_input = ADAPTER.build_input(source(max_posts_per_run=7), since_hours=14)
    assert run_input == {
        "startUrls": [PAGE], "resultsLimit": 7, "onlyPostsNewerThan": "14 hours", "maxItems": 7,
    }


# -- accepting -------------------------------------------------------------------
def test_a_verified_post_is_normalised():
    verdict = judge(post(link="https://news.example.org/story"))
    assert verdict.action == ACCEPT
    report = verdict.report
    assert report.external_id == "facebook:9001"
    assert report.url == f"{PAGE}/posts/9001"
    assert report.published_at == datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
    assert report.content_kind == "social_post"
    assert report.linked_article_url == "https://news.example.org/story"
    assert report.title.startswith("Kombi overturned")
    # engagement numbers are neither needed nor kept
    assert "likes" not in report.extra and "comments" not in report.extra


def test_the_numeric_id_is_learned_only_when_the_page_address_matches():
    assert judge(post()).learned_account_id == "555"
    assert judge(post(), source(platform_account_id="555")).learned_account_id is None


def test_links_back_into_facebook_are_not_external_articles():
    assert judge(post(link="https://l.facebook.com/l.php?u=x")).report.linked_article_url is None
    assert judge(post(link="https://www.facebook.com/other")).report.linked_article_url is None


def test_reshares_are_recorded_but_not_followed():
    verdict = judge(post(sharedPostUrl="https://www.facebook.com/someoneelse/posts/1"))
    assert verdict.action == ACCEPT
    assert verdict.report.extra["shared_post_url"].endswith("/someoneelse/posts/1")


def test_long_text_is_truncated():
    verdict = ADAPTER.judge(post(text="x" * 9000), source(), max_chars=100)
    assert len(verdict.report.text) <= 101


@pytest.mark.parametrize("value", ["not a date", None, "2999-01-01T00:00:00Z"])
def test_unusable_dates_become_none(value):
    item = post(time=value)
    item.pop("timestamp", None)
    assert judge(item).report.published_at is None


def test_timestamp_is_used_when_time_is_missing():
    when = datetime.now(UTC) - timedelta(hours=1)
    item = post(time=None, timestamp=int(when.timestamp()))
    assert abs((judge(item).report.published_at - when).total_seconds()) < 2


# -- rejecting -------------------------------------------------------------------
def test_a_post_from_another_page_is_rejected():
    other = post(pageId="777", pageUrl="https://www.facebook.com/otherpage", url="https://www.facebook.com/otherpage/posts/9001")
    assert judge(other).action == REJECT
    assert judge(other, source(platform_account_id="555")).reason == "origin_mismatch"


def test_a_known_account_id_beats_a_matching_address():
    assert judge(post(pageId="777"), source(platform_account_id="555")).action == REJECT


def test_group_posts_are_rejected():
    verdict = judge(post(url="https://www.facebook.com/groups/123/posts/9001"))
    assert (verdict.action, verdict.reason) == (REJECT, "group_post")


def test_a_disabled_source_accepts_nothing():
    assert judge(post(), source(enabled=False)).reason == "source_disabled"


# -- quarantining ----------------------------------------------------------------
def test_unknown_origin_is_quarantined_not_assumed():
    verdict = judge(post(pageId=None, pageUrl=None))
    assert (verdict.action, verdict.reason) == (QUARANTINE, "origin_unverifiable")
    assert verdict.external_id == "9001"


def test_the_requested_address_is_not_evidence_of_origin():
    """facebookUrl is our own input echoed back; only pageId / pageUrl say who posted."""
    assert judge(post(pageId=None, pageUrl=None, facebookUrl=PAGE)).action == QUARANTINE


def test_an_address_of_a_different_kind_cannot_confirm_origin():
    # The Page is configured by name, the post names it by numeric id: not provable without the id.
    item = post(pageId="555", pageUrl="https://www.facebook.com/profile.php?id=555")
    assert judge(item).action == QUARANTINE
    assert judge(item, source(platform_account_id="555")).action == ACCEPT


def test_a_post_url_belonging_to_another_account_is_quarantined():
    item = post(url="https://www.facebook.com/otherpage/posts/9001")
    assert judge(item).reason == "post_url_other_account"


def test_non_facebook_post_urls_and_missing_identity_are_quarantined():
    assert judge(post(url="https://evil.example.com/p/1")).reason == "post_url_not_facebook"
    assert judge(post(postId=None)).reason == "missing_post_identity"
    assert judge(post(url="")).reason == "missing_post_identity"


def test_opaque_share_urls_pass_when_the_page_itself_is_verified():
    assert judge(post(url="https://www.facebook.com/share/p/abc123/")).action == ACCEPT


# -- ignoring --------------------------------------------------------------------
def test_media_only_posts_are_ignored():
    assert judge(post(text=None)).action == IGNORE
    assert judge(post(text="   ")).action == IGNORE


# -- Actor status rows -----------------------------------------------------------
def test_status_rows_are_not_posts():
    assert ADAPTER.notice(post()) is None
    blocked = ADAPTER.notice({"dataType": "note", "reason": "blocked", "message": "security check"})
    assert blocked.blocking
    harmless = ADAPTER.notice({"dataType": "note", "reason": "no-posts-in-range", "message": "nothing new"})
    assert not harmless.blocking


# -- scheduling ------------------------------------------------------------------
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def test_due_logic():
    retry = timedelta(minutes=30)
    assert is_due(source(), NOW, retry)  # never polled
    assert not is_due(source(last_polled_at=NOW - timedelta(minutes=119)), NOW, retry)
    assert is_due(source(last_polled_at=NOW - timedelta(minutes=121)), NOW, retry)
    failing = source(last_polled_at=NOW - timedelta(minutes=45), collection_status="error")
    assert is_due(failing, NOW, retry)  # a failure is retried sooner than the interval
    blocked = source(last_polled_at=NOW - timedelta(minutes=45), collection_status="blocked")
    assert not is_due(blocked, NOW, retry)  # a refusal is not hammered


def test_the_look_back_window_follows_the_last_success():
    assert since_hours(source(), NOW, 48) == 48
    assert since_hours(source(last_success_at=NOW - timedelta(hours=2)), NOW, 48) == 8
    assert since_hours(source(last_success_at=NOW - timedelta(days=90)), NOW, 48) == 24 * 14


# -- Apify runner (stubbed client; nothing is sent) --------------------------------
class _Run:
    def __init__(self, status):
        self.id, self.status, self.default_dataset_id = "run1", status, "ds1"


class _StubClient:
    def __init__(self, status="SUCCEEDED", rows=()):
        self.status, self.rows, self.call_kwargs, self.actor_path, self.limit = status, list(rows), None, None, None

    def actor(self, path):
        self.actor_path = path
        stub = self

        class _Actor:
            def call(self, **kwargs):
                stub.call_kwargs = kwargs
                return _Run(stub.status)

        return _Actor()

    def dataset(self, _id):
        stub = self

        class _Dataset:
            def iterate_items(self, **kwargs):
                stub.limit = kwargs.get("limit")
                return iter(stub.rows)

        return _Dataset()


def _runner(client):
    from app.ingestion.social.runner import ApifyActorRunner

    runner = ApifyActorRunner.__new__(ApifyActorRunner)
    runner._client = client
    return runner


def test_runner_sends_cost_limits_and_returns_rows():
    client = _StubClient(rows=[{"postId": "1"}])
    rows = _runner(client).run("owner/actor", {"a": 1}, max_items=5, timeout_seconds=120, max_charge_usd=0.25)
    assert rows == [{"postId": "1"}] and client.actor_path == "owner~actor"
    kwargs = client.call_kwargs
    assert kwargs["max_items"] == 5 and kwargs["run_input"] == {"a": 1}
    assert str(kwargs["max_total_charge_usd"]) == "0.25" and kwargs["run_timeout"] == timedelta(seconds=120)
    assert client.limit == 25


def test_runner_fails_on_an_unsuccessful_run():
    from app.ingestion.social.runner import ActorRunError

    with pytest.raises(ActorRunError, match="TIMED-OUT"):
        _runner(_StubClient(status="TIMED-OUT")).run("o/a", {}, max_items=1, timeout_seconds=60, max_charge_usd=0.1)


def test_runner_requires_a_token():
    from app.ingestion.social.runner import ApifyActorRunner

    with pytest.raises(ValueError):
        ApifyActorRunner("")
