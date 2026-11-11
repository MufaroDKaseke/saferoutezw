"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { SearchField, SelectField, FilterBar, RANGE_OPTIONS } from "@/components/shared/filters";
import { EmptyState, QueryError, TableSkeleton } from "@/components/shared/states";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { listSources } from "@/lib/api/sources";
import { listNewsroomArticles } from "@/lib/api/newsroom";
import { formatShort } from "@/lib/formatters/date";
import {
  ARTICLE_STATE_OPTIONS,
  NEWS_CATEGORY_OPTIONS,
  REVIEW_STATUS_OPTIONS,
  geographicLabel,
  type ArticleState,
  type ReviewStatus,
} from "@/lib/newsroom/taxonomy";
import { AttentionBadge, ArticleStateBadge, BasisNote, NewsCategoryBadge, ReviewStatusBadge } from "./badges";

const PAGE_SIZE = 15;
const RANGE_MS = { "24h": 24 * 3600_000, "7d": 7 * 24 * 3600_000, "30d": 30 * 24 * 3600_000 } as const;
type Range = keyof typeof RANGE_MS;

/** NUST FM News Monitor: every collected article, its AI summary and category, searchable and filterable. */
export function NewsroomMonitor() {
  const list = useListState({
    search: "",
    publisherId: undefined as string | undefined,
    category: undefined as string | undefined,
    state: undefined as ArticleState | undefined,
    reviewStatus: undefined as ReviewStatus | undefined,
    range: undefined as Range | undefined,
  });
  const { filters, page, setPage } = list;
  const search = useDebouncedValue(filters.search);

  const publishers = useResource("newsroom:publishers", () => listSources());
  // The request key holds the chosen range, not a timestamp, so it stays stable between renders;
  // the cut-off time is worked out when the request is made.
  const query = {
    page,
    pageSize: PAGE_SIZE,
    q: search || undefined,
    publisherId: filters.publisherId,
    category: filters.category,
    state: filters.state,
    reviewStatus: filters.reviewStatus,
    range: filters.range,
  };
  const articles = useResource(`newsroom:articles:${JSON.stringify(query)}`, () => {
    const { range, ...rest } = query;
    return listNewsroomArticles({
      ...rest,
      collectedFrom: range ? new Date(Date.now() - RANGE_MS[range]).toISOString() : undefined,
    });
  });
  const data = articles.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <PageHeader
        title="NUST FM — News Monitor"
        description="Articles collected from Zimbabwean news feeds, classified by AI. Summaries and categories are machine readings of the article text: check the original before using anything on air."
      />

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField
          label="Search headlines and text"
          value={filters.search}
          onChange={(v) => list.setFilter("search", v)}
          placeholder="e.g. budget, NUST, Bulawayo"
        />
        <SelectField
          label="Publisher"
          value={filters.publisherId}
          onChange={(v) => list.setFilter("publisherId", v)}
          options={(publishers.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
          allLabel="All publishers"
        />
        <SelectField
          label="Category"
          value={filters.category}
          onChange={(v) => list.setFilter("category", v)}
          options={NEWS_CATEGORY_OPTIONS}
          allLabel="All categories"
        />
        <SelectField
          label="Processing"
          value={filters.state}
          onChange={(v) => list.setFilter("state", v)}
          options={ARTICLE_STATE_OPTIONS}
          allLabel="Any state"
        />
        <SelectField
          label="Review"
          value={filters.reviewStatus}
          onChange={(v) => list.setFilter("reviewStatus", v)}
          options={REVIEW_STATUS_OPTIONS}
          allLabel="Any review status"
        />
        <SelectField
          label="Collected"
          value={filters.range}
          onChange={(v) => list.setFilter("range", v)}
          options={RANGE_OPTIONS}
          allLabel="Any time"
        />
      </FilterBar>

      {articles.error ? (
        <QueryError error={articles.error} onRetry={articles.refetch} what="articles" />
      ) : !data ? (
        <TableSkeleton rows={6} cols={4} />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No articles match these filters"
          description="Articles appear here after the RSS feeds have been collected. Try clearing the filters."
        />
      ) : (
        <>
          <ul className="divide-y divide-slate-100 rounded-xl bg-card ring-1 ring-foreground/10" aria-label="Articles">
            {data.items.map((a) => (
              <li key={a.id} className="space-y-2 px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <NewsCategoryBadge category={a.category} />
                  {a.secondary_category ? <NewsCategoryBadge category={a.secondary_category} /> : null}
                  <ArticleStateBadge state={a.state} />
                  <ReviewStatusBadge status={a.review.status} />
                  <AttentionBadge article={a} />
                </div>
                <h2 className="text-[15px] leading-snug font-semibold">
                  <Link href={`/news/${a.id}`} className="hover:underline">
                    {a.headline}
                  </Link>
                </h2>
                {a.summary ? <p className="max-w-3xl text-sm text-slate-700">{a.summary}</p> : null}
                <p className="tnum flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
                  <span className="font-medium">{a.publisher}</span>
                  <span>Published {formatShort(a.published_at, "date not given")}</span>
                  <span>Collected {formatShort(a.collected_at)}</span>
                  {a.geographic_relevance ? <span>{geographicLabel(a.geographic_relevance)}</span> : null}
                  <BasisNote basis={a.classification_basis} />
                  {a.source_url ? (
                    <a
                      href={a.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 font-medium text-emerald-800 hover:underline"
                    >
                      Original article <ExternalLink className="size-3" aria-hidden />
                    </a>
                  ) : null}
                </p>
              </li>
            ))}
          </ul>
          <nav className="flex items-center justify-between text-sm text-slate-600" aria-label="Pagination">
            <span className="tnum">
              {data.total.toLocaleString()} articles · page {data.page} of {pages}
            </span>
            <span className="flex gap-2">
              <Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </span>
          </nav>
        </>
      )}
    </div>
  );
}
