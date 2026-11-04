"use client";

import Link from "next/link";
import { useMemo } from "react";
import { BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, SearchField, SelectField } from "@/components/shared/filters";
import { ConfidenceBar } from "@/components/shared/meter";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, QueryError } from "@/components/shared/states";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { getIntelligenceCategories, listIntelligence, type IntelligenceSummary } from "@/lib/api/intelligence";
import { formatShort } from "@/lib/formatters/date";
import { RECORD_STATUS_LABEL } from "@/lib/domain/intelligence";
import { RECORD_KIND_LABELS, RECORD_KINDS, RECORD_STATUSES } from "@/lib/taxonomy.generated";
import { CategoryBadge, RecordKindBadge, RecordStatusBadge, ScopeText } from "./badges";
import { CategoryFilter, type CategoryFilterValue } from "./category-filter";

const helper = columnHelper<IntelligenceSummary>();
const PAGE_SIZE = 10;

const KIND_OPTIONS = RECORD_KINDS.map((value) => ({ value, label: RECORD_KIND_LABELS[value] }));
const STATUS_OPTIONS = RECORD_STATUSES.map((value) => ({ value, label: RECORD_STATUS_LABEL[value] }));

export function IntelligenceList() {
  const list = useListState(
    {
      search: "",
      category: "all" as CategoryFilterValue,
      recordKind: undefined as string | undefined,
      status: undefined as string | undefined,
    },
    { id: "created", dir: "desc" },
  );
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const query = {
    q: search || undefined,
    category: filters.category === "all" ? undefined : filters.category,
    recordKind: filters.recordKind,
    status: filters.status,
    page: list.page,
    pageSize: PAGE_SIZE,
  };
  const records = useResource(`intelligence:${JSON.stringify(query)}`, () => listIntelligence(query));
  const categories = useResource("intelligence:categories", () => getIntelligenceCategories());

  const counts = useMemo(() => {
    const byCategory = Object.fromEntries((categories.data?.categories ?? []).map((c) => [c.category, c.total]));
    const total = Object.values(byCategory).reduce((n, v) => n + v, 0);
    return categories.data ? { ...byCategory, all: total } : undefined;
  }, [categories.data]);

  const columns = useMemo(
    () => [
      helper.display({
        id: "headline",
        header: "Record",
        cell: ({ row }) => (
          <div className="min-w-0">
            <Link href={`/intelligence/${row.original.id}`} className="text-sm leading-snug font-semibold underline-offset-2 hover:underline">
              {row.original.headline}
            </Link>
            <p className="mt-1 line-clamp-2 text-xs text-slate-600">{row.original.summary}</p>
          </div>
        ),
      }),
      helper.display({
        id: "category",
        header: "Category",
        cell: ({ row }) => (
          <div className="space-y-1.5">
            <CategoryBadge category={row.original.primary_category} subtype={row.original.primary_subtype} />
            <div>
              <RecordKindBadge kind={row.original.record_kind} />
            </div>
          </div>
        ),
      }),
      helper.display({
        id: "scope",
        header: "Place and date",
        cell: ({ row }) => (
          <div className="space-y-0.5 text-sm">
            <ScopeText scope={row.original.geographic_scope} />
            <p className="text-xs text-slate-600">
              {[row.original.road_name, row.original.district_or_town, row.original.province].filter(Boolean).join(", ") || "No place stated"}
            </p>
            <p className="tnum text-xs text-slate-600">{row.original.event_date ? `Dated ${formatShort(row.original.event_date)}` : "Date not stated"}</p>
          </div>
        ),
      }),
      helper.display({
        id: "source",
        header: "Source",
        cell: ({ row }) => (
          <div className="text-sm">
            <p className="font-medium">{row.original.publisher}</p>
            <p className="tnum text-xs text-slate-600">{formatShort(row.original.source_published_at)}</p>
          </div>
        ),
      }),
      helper.display({
        id: "confidence",
        header: "AI confidence",
        cell: ({ row }) => <ConfidenceBar value={row.original.classification_confidence} />,
      }),
      helper.display({
        id: "status",
        header: "Editorial status",
        cell: ({ row }) => (
          <div className="space-y-1">
            <RecordStatusBadge status={row.original.status} />
            {row.original.published_outputs.length > 0 ? (
              <p className="text-xs text-slate-600">Published as {row.original.published_outputs.length} output(s)</p>
            ) : null}
          </div>
        ),
      }),
    ],
    [],
  );

  const data = records.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Transport Intelligence"
        description="Classified transport, traffic and road-safety reports. Specific road events can become incident candidates; policy, statistics, projects and campaigns stay here as reviewable intelligence. Everything is an unverified AI reading until an editor approves it."
        actions={
          <Button asChild variant="outline">
            <Link href="/intelligence/statistics">
              <BarChart3 aria-hidden /> Statistics and trends
            </Link>
          </Button>
        }
      />
      <CategoryFilter value={filters.category} onChange={(v) => list.setFilter("category", v)} counts={counts} />
      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search headline or summary" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. toll, Beitbridge" className="lg:col-span-2" />
        <SelectField label="Record kind" value={filters.recordKind} onChange={(v) => list.setFilter("recordKind", v)} options={KIND_OPTIONS} allLabel="All kinds" />
        <SelectField label="Editorial status" value={filters.status} onChange={(v) => list.setFilter("status", v)} options={STATUS_OPTIONS} allLabel="All statuses" />
      </FilterBar>
      <Card className="gap-0 overflow-hidden py-0">
        {records.error ? (
          <QueryError error={records.error} onRetry={records.refetch} />
        ) : (
          <DataTable
            caption="Classified transport intelligence records"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(r) => r.id}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["record", "records"]}
            isLoading={records.isLoading}
            isFetching={records.isFetching}
            rowHref={(r) => `/intelligence/${r.id}`}
            minWidth={1000}
            empty={
              <EmptyState
                title="No intelligence records match these filters"
                description="Records appear here after the pipeline has classified a relevant article. Try another category or clear the filters."
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
