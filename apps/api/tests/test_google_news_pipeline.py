"""Resolver integration against the disposable test DB; network/AI use synthetic fixtures."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select, text

import db_factories as f
from app.core.config import Settings
from app.ingestion.article import ArticleFetchError, ArticleFetcher
from app.ingestion.google_news import GoogleNewsArticleFetcher, GoogleNewsResolver, _PublisherFetcher
from app.ingestion.rss import RssIngestor, SourceRef, canonicalize_url
from app.jobs import pipeline_job
from app.models import ExtractionRun, SourceItem
from app.services.pipeline import PipelineRunner
from feed_server import article_page, rss_document
from newsroom_helpers import FakeNewsroomExtractor, classification
from test_article_pipeline import FakeFetch, add_item
from test_google_news import BODY, GOOGLE, PUBLISHER, SIGNATURE, Session, public_dns, response, rpc_response


def wrapped(*, replies=None, publisher_replies=None, ordinary=None):
    return GoogleNewsArticleFetcher(
        ordinary or FakeFetch(default=BODY), enabled=True,
        resolver=GoogleNewsResolver(session=Session(*(replies or [response(SIGNATURE), rpc_response()])), delay=0),
        publisher=_PublisherFetcher(
            session=Session(*(publisher_replies or [response(article_page("Budget debate", [BODY]))])), delay=0,
        ),
    )


def run(engine, fetch, extractor=None, **options):
    return PipelineRunner(engine, fetch_article=fetch, extractor=extractor, newsroom=True, **options).run()


def test_google_rss_to_publisher_to_classifier_preserves_identity_and_repeat_poll_dedup(
    session, migrated_engine, feed_server, public_dns,
):
    source = f.make_source(session)
    source.name = "Techzim"
    published = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
    source.feed_url = feed_server.serve("/google-feed", rss_document([
        {"title": "Budget debate", "guid": "google-guid-1", "link": GOOGLE, "published": published},
    ]))
    session.commit()
    source_before = session.execute(text('SELECT to_jsonb(s) FROM sources s WHERE id=:id'), {'id': source.id}).scalar_one()
    history = f.make_source_item(
        session, source, processing_status="processed", source_metadata={"classification": {"summary": "Historical result"}},
    )
    session.commit()
    history_before = session.execute(text('SELECT to_jsonb(s) FROM source_items s WHERE id=:id'), {'id': history.id}).scalar_one()
    ref = SourceRef(source.id, source.name, source.feed_url)
    ingestor = RssIngestor(migrated_engine)
    assert ingestor.ingest(ref).inserted == 1
    extractor = FakeNewsroomExtractor(classification())
    summary = run(migrated_engine, wrapped(), extractor)
    session.expire_all()
    item = session.scalars(select(SourceItem).where(SourceItem.external_id == "google-guid-1")).one()
    assert (summary.fetched, summary.extracted) == (1, 1)
    assert item.processing_status == "processed" and item.fetch_status == "ok"
    assert item.canonical_url == canonicalize_url(GOOGLE) and item.source_metadata["url"] == item.canonical_url
    assert item.external_id == "google-guid-1" and item.source_id == source.id and item.published_at == published
    assert item.source_metadata["article_url"] == PUBLISHER
    assert item.source_metadata["google_news"] == {
        "status": "resolved", "original_url": item.canonical_url,
        "resolved_url": PUBLISHER, "publisher_url": canonicalize_url(PUBLISHER),
    }
    assert extractor.calls[0].source_name == "Techzim" and extractor.calls[0].published == published
    assert "budget debate" in extractor.calls[0].text and "data-n-a-sg" not in extractor.calls[0].text
    assert item.source_metadata["classification"]["basis"] == "full_text"
    repeat = ingestor.ingest(ref)
    assert (repeat.inserted, repeat.duplicates) == (0, 1)
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 2  # one history + one RSS item
    assert session.execute(text('SELECT to_jsonb(s) FROM sources s WHERE id=:id'), {'id': source.id}).scalar_one() == source_before
    assert session.execute(text('SELECT to_jsonb(s) FROM source_items s WHERE id=:id'), {'id': history.id}).scalar_one() == history_before


@pytest.mark.parametrize("failure", ["signature", "publisher_403", "unsafe_destination", "timeout", "challenge", "error_page"])
def test_a_google_failure_never_reaches_ai_and_does_not_stop_an_ordinary_article(
    session, migrated_engine, public_dns, failure,
):
    bad = add_item(session, title="Budget debate", url=GOOGLE, excerpt="Google intermediary feed summary")
    good = add_item(session, title="Ordinary budget report", url="https://ordinary.example/budget")
    options = {}
    if failure == "signature":
        options['replies'] = [response(article_page("Google News", [BODY]))]
    elif failure == "publisher_403":
        options['publisher_replies'] = [response(BODY, status=403)]
    elif failure == "unsafe_destination":
        options['replies'] = [response(SIGNATURE), rpc_response("http://169.254.169.254/latest/meta-data/")]
    elif failure == "timeout":
        options['replies'] = [ArticleFetchError("lookup timed out", transient=True)]
    elif failure == "challenge":
        options['publisher_replies'] = [response('<title>Just a moment...</title><article>' + BODY + '</article>')]
    else:
        options['publisher_replies'] = [response('<title>404 Not Found</title><article>' + BODY + '</article>')]
    extractor = FakeNewsroomExtractor(classification())
    summary = run(migrated_engine, wrapped(**options), extractor, max_attempts=1)
    session.expire_all()
    assert bad.processing_status == "fetch_failed" and bad.fetch_status == "failed" and bad.fetch_error
    assert bad.article_text_redacted is None and "classification" not in bad.source_metadata
    assert bad.source_metadata['google_news']['original_url'] == GOOGLE
    if failure == "publisher_403":
        assert bad.source_metadata['google_news']['status'] == 'access_restricted' and 'HTTP 403' in bad.fetch_error
        assert bad.source_metadata['google_news']['resolved_url'] == PUBLISHER
    assert good.processing_status == "processed" and len(extractor.calls) == 1
    assert extractor.calls[0].title == good.title_redacted
    assert (summary.fetch_failed, summary.extracted) == (1, 1)


def test_a_transient_google_failure_retries_without_classifying_an_excerpt(session, migrated_engine):
    item = add_item(session, url=GOOGLE)
    resolver = SimpleNamespace(resolve=Mock(side_effect=[ArticleFetchError("timeout", transient=True), PUBLISHER]))
    fetch = GoogleNewsArticleFetcher(FakeFetch(), enabled=True, resolver=resolver, publisher=FakeFetch(default=BODY))
    extractor = FakeNewsroomExtractor(classification())
    first = run(migrated_engine, fetch, extractor)
    session.refresh(item)
    assert first.fetch_retry == 1 and item.processing_status == 'screened' and extractor.calls == []
    second = run(migrated_engine, fetch, extractor)
    session.refresh(item)
    assert second.extracted == 1 and item.processing_status == 'processed'
    assert item.source_metadata['google_news']['status'] == 'resolved'


@pytest.mark.parametrize('first_is_google', [False, True])
def test_two_urls_for_one_publisher_article_do_not_classify_it_twice(session, migrated_engine, first_is_google):
    source = f.make_source(session)
    first_url = GOOGLE if first_is_google else PUBLISHER
    first = add_item(session, source, url=first_url)
    resolve = SimpleNamespace(resolve=Mock(return_value=PUBLISHER))
    # Different fetched text proves de-duplication is by resolved URL, not just content hash.
    publisher = FakeFetch(default=BODY)
    fetch = GoogleNewsArticleFetcher(FakeFetch(default=BODY), enabled=True, resolver=resolve, publisher=publisher)
    extractor = FakeNewsroomExtractor(classification())
    assert run(migrated_engine, fetch, extractor).extracted == 1
    publisher.default = BODY + ' Additional text now present on the publisher page.'
    second_url = GOOGLE.replace('CBMi_test', 'CBMi_another')
    second = add_item(session, source, url=second_url)
    summary = run(migrated_engine, fetch, extractor)
    session.expire_all()
    assert first.processing_status == 'processed' and second.processing_status == 'discarded'
    assert second.canonical_url == second_url and second.source_id == source.id
    assert second.source_metadata['google_news']['duplicate_of'] == str(first.id)
    assert second.source_metadata['google_news']['original_url'] == second_url
    assert summary.discarded == 1 and len(extractor.calls) == 1
    assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 1


def test_disabling_resolution_blocks_google_but_leaves_normal_fetching_working(session, migrated_engine):
    bad = add_item(session, url=GOOGLE)
    good = add_item(session)
    ordinary, resolver = FakeFetch(default=BODY), Mock()
    fetch = GoogleNewsArticleFetcher(ordinary, enabled=False, resolver=resolver)
    extractor = FakeNewsroomExtractor(classification())
    run(migrated_engine, fetch, extractor)
    session.expire_all()
    assert bad.processing_status == 'fetch_failed' and 'disabled' in bad.fetch_error
    assert good.processing_status == 'processed' and ordinary.calls == [good.canonical_url]
    resolver.resolve.assert_not_called()


def test_normal_rss_to_article_to_ai_stays_on_the_original_path(session, migrated_engine, feed_server):
    article_url = feed_server.serve_html('/ordinary-article', article_page('Budget debate', [BODY]))
    feed_url = feed_server.serve('/ordinary-rss', rss_document([
        {'title': 'Budget debate', 'guid': 'ordinary-guid', 'link': article_url},
    ]))
    source = f.make_source(session)
    source.feed_url = feed_url
    session.commit()
    ingestor = RssIngestor(migrated_engine)
    ref = SourceRef(source.id, source.name, source.feed_url)
    assert ingestor.ingest(ref).inserted == 1
    original = Mock(wraps=ArticleFetcher(allow_private_hosts=True, delay=0))
    resolver = SimpleNamespace(resolve=Mock(side_effect=AssertionError('normal RSS must not resolve')))
    fetch = GoogleNewsArticleFetcher(original, enabled=True, resolver=resolver)
    extractor = FakeNewsroomExtractor(classification())
    summary = run(migrated_engine, fetch, extractor)
    item = session.scalars(select(SourceItem)).one()
    session.refresh(item)
    assert (summary.fetched, summary.extracted) == (1, 1)
    original.assert_called_once_with(article_url)
    resolver.resolve.assert_not_called()
    assert fetch._publisher is None and 'google_news' not in item.source_metadata
    assert item.canonical_url == article_url and item.source_metadata['article_url'] == article_url
    assert feed_server.hits['/ordinary-article'] == 1
    assert ingestor.ingest(ref).duplicates == 1


def test_the_job_wires_an_explicit_opt_in_and_preserves_existing_fetch_limits(monkeypatch):
    monkeypatch.setattr(pipeline_job, 'get_engine', lambda: object())
    assert Settings(_env_file=None).google_news_resolution_enabled is False
    for enabled in [False, True]:
        settings = Settings(_env_file=None, google_news_resolution_enabled=enabled, article_fetch_timeout_seconds=7)
        fetch = pipeline_job.build_runner(settings)._fetch_article
        assert isinstance(fetch, GoogleNewsArticleFetcher) and fetch._enabled is enabled
        assert isinstance(fetch._ordinary, ArticleFetcher) and fetch._ordinary._timeout == 7
