"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { RotateCw, Tags } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, RANGE_OPTIONS, SearchField, SelectField, FilterField } from "@/components/shared/filters";
import { Input } from "@/components/ui/input";
import { ConfidenceBar } from "@/components/shared/meter";
import { PageHeader } from "@/components/shared/page-header";
import { QueryError, EmptyState } from "@/components/shared/states";
import { Chip, ExtractionBadge, RetrievalBadge, WorkflowBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { listNews, retryNewsProcessing } from "@/lib/api/news";
import { listSources } from "@/lib/api/sources";
import type { DateRangeKey } from "@/lib/api/types";
import { formatShort } from "@/lib/formatters/date";
import { SOURCE_KIND_LABEL, WORKFLOW_LABEL } from "@/lib/formatters/labels";
import type { ArticleWorkflowState, SourceItem } from "@/types";
import { CategoryFilter, type CategoryFilterValue } from "@/components/intelligence/category-filter";
import { CategoryBadge, ClassificationStatusBadge, RecordKindBadge, RecordStatusBadge, ScopeText } from "@/components/intelligence/badges";
import { categoryLabel } from "@/lib/domain/intelligence";
import { KeywordChips } from "./keyword-chips";

const helper = columnHelper<SourceItem>();

const STATUS_OPTIONS = (Object.keys(WORKFLOW_LABEL) as ArticleWorkflowState[]).map((value) => ({
  value,
  label: WORKFLOW_LABEL[value],
}));

const PAGE_SIZE = 10;

export function NewsMonitor() {
  const list = useListState(
    {
      search: "",
      publisherId: undefined as string | undefined,
      relevance: undefined as "relevant" | "not_relevant" | undefined,
      status: undefined as ArticleWorkflowState | undefined,
      range: undefined as DateRangeKey | undefined,
      keyword: "",
      category: "all" as CategoryFilterValue,
    },
    { id: "receivedAt", dir: "desc" },
  );
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const keyword = useDebouncedValue(filters.keyword);
  const [retrying, setRetrying] = useState<string | null>(null);

  const sources = useResource("news:sources", () => listSources());
  const query = {
    search,
    keyword,
    publisherId: filters.publisherId,
    relevance: filters.relevance,
    status: filters.status,
    range: filters.range,
    category: filters.category === "all" ? undefined : filters.category,
    page: list.page,
    pageSize: PAGE_SIZE,
    sort: list.sort?.id,
    dir: list.sort?.dir,
  };
  const news = useResource(`news:${JSON.stringify(query)}`, () => listNews(query));

  const retry = async (item: SourceItem) => {
    setRetrying(item.id);
    try {
      const result = await retryNewsProcessing(item.id);
      toast.success(result.message);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setRetrying(null);
    }
  };

  const columns = useMemo(
    () => [
      helper.display({
        id: "title",
        header: "Article and status",
        cell: ({ row }) => (
          <div className="min-w-0">
            <Link
              href={`/news/${row.original.id}`}
              className="text-sm leading-snug font-semibold text-foreground underline-offset-2 hover:underline"
            >
              {row.original.titleRedacted}
            </Link>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              <WorkflowBadge state={row.original.workflowState} />
              {row.original.linkedIncidentIds.length > 0 ? (
                <span className="text-xs text-slate-600">
                  Evidence for {row.original.linkedIncidentIds.length}{" "}
                  {row.original.linkedIncidentIds.length === 1 ? "incident" : "incidents"}
                </span>
              ) : null}
            </div>
          </div>
        ),
      }),
      helper.display({
        id: "publisher",
        header: "Publisher",
        cell: ({ row }) => (
          <div>
            <p className="text-sm font-medium">{row.original.publisherName}</p>
            <p className="text-xs text-slate-600">{SOURCE_KIND_LABEL[row.original.sourceKind]}</p>
          </div>
        ),
      }),
      helper.display({
        id: "received",
        header: "Published / received",
        cell: ({ row }) => (
          <div className="tnum text-sm">
            <p>{formatShort(row.original.publishedAt)}</p>
            <p className="text-xs text-slate-600">Received {formatShort(row.original.receivedAt)}</p>
          </div>
        ),
      }),
      helper.display({
        id: "score",
        header: "Keyword relevance",
        cell: ({ row }) => {
          const s = row.original.screening;
          if (!s) return <span className="text-sm text-slate-600">Not screened yet</span>;
          return (
            <div className="space-y-1.5">
              {s.score !== null ? <ConfidenceBar value={s.score} /> : null}
              <div className="flex flex-wrap items-center gap-2">
                <Chip tone={s.decision === "relevant" ? "slate" : "slate"} className={s.decision === "relevant" ? "bg-slate-900 text-white" : undefined}>
                  {s.decision === "relevant" ? "Relevant" : "Not relevant"}
                </Chip>
                {s.matchedKeywords.length > 0 ? (
                  <Popover>
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded text-xs font-medium text-emerald-800 hover:underline focus-visible:outline-2"
                      >
                        <Tags className="size-3" aria-hidden />
                        {s.matchedKeywords.length} {s.matchedKeywords.length === 1 ? "keyword" : "keywords"}
                      </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" className="w-80 gap-3 p-4">
                      <h3 className="text-sm font-bold">Matched keywords</h3>
                      <KeywordChips keywords={s.matchedKeywords} />
                      <p className="text-xs text-slate-600">A keyword match means the article was read further. It does not show that an accident happened.</p>
                    </PopoverContent>
                  </Popover>
                ) : null}
              </div>
            </div>
          );
        },
      }),
      helper.display({
        id: "classification",
        header: "Category",
        cell: ({ row }) => <ClassificationCell item={row.original} />,
      }),
      helper.display({
        id: "retrieval",
        header: "Full article",
        cell: ({ row }) => <RetrievalBadge status={row.original.retrievalStatus} />,
      }),
      helper.display({
        id: "extraction",
        header: "AI extraction",
        cell: ({ row }) => <ExtractionBadge status={row.original.extractionStatus} />,
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-2">
            {row.original.workflowState === "failed" ? (
              <Button
                variant="outline"
                size="icon-sm"
                disabled={retrying === row.original.id}
                onClick={() => retry(row.original)}
                aria-label={`Retry processing: ${row.original.titleRedacted}`}
                title="Retry processing"
              >
                <RotateCw aria-hidden />
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link href={`/news/${row.original.id}`}>
                Open<span className="sr-only"> {row.original.titleRedacted}</span>
              </Link>
            </Button>
          </div>
        ),
      }),
    ],
    [retrying],
  );

  const data = news.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="News Monitor"
        description="Posts found by monitored sources and their progress."
      />

      <CategoryFilter value={filters.category} onChange={(v) => list.setFilter("category", v)} />

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search headline" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. Rusape, bus, collision" className="lg:col-span-2" />
        <SelectField
          label="Publisher"
          value={filters.publisherId}
          onChange={(v) => list.setFilter("publisherId", v)}
          options={(sources.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
          allLabel="All publishers"
        />
        <SelectField
          label="Relevance"
          value={filters.relevance}
          onChange={(v) => list.setFilter("relevance", v)}
          options={[
            { value: "relevant", label: "Relevant" },
            { value: "not_relevant", label: "Not relevant" },
          ]}
          allLabel="All"
        />
        <SelectField label="Processing status" value={filters.status} onChange={(v) => list.setFilter("status", v)} options={STATUS_OPTIONS} allLabel="All statuses" />
        <SelectField label="Date received" value={filters.range} onChange={(v) => list.setFilter("range", v)} options={RANGE_OPTIONS} allLabel="Any time" />
        <FilterField label="Keyword match" htmlFor="kw">
          <Input id="kw" value={filters.keyword} onChange={(e) => list.setFilter("keyword", e.target.value)} placeholder="e.g. minibus" autoComplete="off" />
        </FilterField>
      </FilterBar>

      <Card className="gap-0 overflow-hidden py-0">
        {news.error ? (
          <QueryError error={news.error} onRetry={news.refetch} />
        ) : (
          <DataTable
            caption="News articles discovered by the RSS pipeline"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(a) => a.id}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["article", "articles"]}
            isLoading={news.isLoading}
            isFetching={news.isFetching}
            sort={list.sort}
            onSortChange={list.setSort}
            sortable={{
              title: { key: "title" },
              publisher: { key: "publisher" },
              received: { key: "receivedAt", firstDir: "desc" },
              score: { key: "score", firstDir: "desc" },
            }}
            rowHref={(a) => `/news/${a.id}`}
            columnClassName={{ title: "w-[26%] min-w-60", classification: "w-[16%] min-w-44", actions: "w-20" }}
            minWidth={1240}
            empty={
              <EmptyState
                title="No articles match these filters"
                description="Try removing a filter or searching for a different road or place."
                action={
                  list.dirty ? (
                    <Button variant="outline" onClick={list.reset}>
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        )}
      </Card>
    </div>
  );
}

/** What the item is about, whether it is an event or background information, and where it stands. */
function ClassificationCell({ item }: { item: SourceItem }) {
  const c = item.classification;
  if (!c) return <span className="text-sm text-slate-600">Not classified</span>;
  if (c.primaryCategory) {
    return (
      <div className="space-y-1.5">
        <CategoryBadge category={c.primaryCategory} subtype={c.primarySubtype} />
        <div className="flex flex-wrap items-center gap-1.5">
          {c.recordKind ? <RecordKindBadge kind={c.recordKind} /> : null}
          {c.editorialStatus ? <RecordStatusBadge status={c.editorialStatus} /> : null}
        </div>
        <ScopeText scope={c.geographicScope} />
        {c.linkedIncidentId ? (
          <Link href={`/incidents/${c.linkedIncidentId}`} className="block text-xs font-semibold text-emerald-800 hover:underline">
            Linked road event
          </Link>
        ) : null}
        {/* Hidden for now: link to the Transport Intelligence record.
        {c.intelligenceRecordId ? (
          <Link href={`/intelligence/${c.intelligenceRecordId}`} className="block text-xs font-semibold text-emerald-800 hover:underline">
            Open intelligence record
          </Link>
        ) : null}
        */}
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <ClassificationStatusBadge status={c.status} />
      {c.candidateCategories.length > 0 ? (
        <p className="text-xs text-slate-600">
          Keyword signals: {c.candidateCategories.map((x) => categoryLabel(x)).join(", ")}
        </p>
      ) : null}
    </div>
  );
}
