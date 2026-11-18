# Google News article links

`GOOGLE_NEWS_RESOLUTION_ENABLED=true` opts the article-fetching pipeline into
Google News resolution. The default is `false`. Only the exact parsed hostname
`news.google.com` is intercepted, with `/rss/articles/<id>`, `/articles/<id>` or
`/read/<id>` required for resolution. Ordinary article URLs go directly to the
original `ArticleFetcher`, with its existing limits and behavior.

The RSS parser, source configurations and polling intervals are unchanged.
Resolution happens after polling and screening, immediately before article
fetching. An HTTP redirect to a public publisher is accepted. Otherwise the
resolver reads Google's per-article signature and timestamp and makes one
`Fbv4je` / `garturlreq` lookup. This is an undocumented Google protocol; its
reference implementation is the [Google News URL decoder](https://github.com/SSujitX/google-news-url-decoder).
If the protocol changes, the individual article fails closed.

Google/publisher requests have bounded timeouts, response sizes and redirect
counts. Every destination must be public HTTP(S), without credentials or unusual
ports. Connections are pinned to a validated public IP while retaining the
original HTTP Host, TLS SNI and certificate verification. Private/mixed DNS
answers, Google consent pages, challenges, errors and HTTP 403 are rejected.
No browser automation or anti-bot bypass is used.

The item keeps its original `canonical_url`, external ID, publisher source ID and
RSS publication date. Existing `source_metadata.article_url` records the final
publisher URL; `source_metadata.google_news` records the original URL, resolution
status and resolved publisher URL. A resolution failure uses the existing
`fetch_failed` status, after bounded retries for transient failures. Google
failures never use the newsroom's headline/excerpt classification fallback.
Ordinary sources keep that fallback unchanged. A publisher's HTTP 403 records
`access_restricted` and is not retried automatically.

Repeat polls retain the existing RSS unique keys. A different Google ID resolving
to an already fetched/processed publisher article in the same source is marked
`discarded`, with `duplicate_of` recorded, and causes no additional classifier
call. Previously stored items are not rewritten or backfilled.

## Enable or roll back

After deploying the tested code, set `GOOGLE_NEWS_RESOLUTION_ENABLED=true` in the
server's existing environment and restart only `saferoute-scheduler` so it reloads
the setting. No schema migration or source update is required.

To disable resolution, set `GOOGLE_NEWS_RESOLUTION_ENABLED=false` and restart
`saferoute-scheduler`. Ordinary RSS collection and article fetching continue
unchanged; Google article links fail closed with `Google News resolution
disabled`. Existing articles and classifications are retained. This switch does
not requeue historical failures.

## Validation

The isolated signature/RPC format follows the
[Google News decoder's protocol implementation](https://github.com/SSujitX/google-news-url-decoder/blob/main/googlenewsdecoder/_parse.py).
The application uses its existing HTTP/parser dependencies and adds no decoder package.

From `apps/api`, using the existing virtual environment:

```text
python -m pytest tests/test_google_news.py tests/test_google_news_pipeline.py tests/test_rss_ingestion.py tests/test_rss_polling.py tests/test_rss_scheduler.py tests/test_feeds_module.py tests/test_pipeline_units.py tests/test_article_pipeline.py tests/test_newsroom_pipeline.py -q
```

Database tests use the disposable `_test` database. The normal-RSS integration
test runs the real poller/parser, original article fetcher and pipeline against
a local HTTP server, and asserts the Google resolver is never called. All Google
protocol responses and classifiers in tests are synthetic; no live model calls
or production database operations are needed.
