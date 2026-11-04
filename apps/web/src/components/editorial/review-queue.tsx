"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, SearchField, SelectField } from "@/components/shared/filters";
import { ConfidenceBar } from "@/components/shared/meter";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote } from "@/components/shared/notes";
import { SegmentedControl } from "@/components/shared/segmented";
import { EmptyState, QueryError } from "@/components/shared/states";
import { PriorityBadge, ReviewStateBadge, RiskBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { getReviewCounts, listReviews } from "@/lib/api/reviews";
import { formatRelative } from "@/lib/formatters/date";
import { INCIDENT_TYPE_LABEL, PRIORITY_LABEL } from "@/lib/formatters/labels";
import type { ReviewPriority, ReviewQueueItem, ReviewState } from "@/types";

const helper = columnHelper<ReviewQueueItem>();
const PAGE_SIZE = 10;

type Tab = "open" | ReviewState;

const PRIORITY_OPTIONS = (Object.keys(PRIORITY_LABEL) as ReviewPriority[]).map((value) => ({ value, label: PRIORITY_LABEL[value] }));

export function ReviewQueue() {
  const list = useListState(
    { search: "", tab: "open" as Tab, priority: undefined as ReviewPriority | undefined },
    { id: "priority", dir: "desc" },
  );
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const counts = useResource("reviews:counts", () => getReviewCounts());

  const query = {
    search,
    state: filters.tab,
    priority: filters.priority,
    page: list.page,
    pageSize: PAGE_SIZE,
    sort: list.sort?.id,
    dir: list.sort?.dir,
  };
  const reviews = useResource(`reviews:${JSON.stringify(query)}`, () => listReviews(query));
  const data = reviews.data;
  const c = counts.data;

  const tabs = [
    { value: "open" as const, label: c ? `Awaiting a decision (${c.pending + c.needs_changes})` : "Awaiting a decision" },
    { value: "pending" as const, label: c ? `Pending (${c.pending})` : "Pending" },
    { value: "needs_changes" as const, label: c ? `Needs changes (${c.needs_changes})` : "Needs changes" },
    { value: "approved" as const, label: c ? `Approved (${c.approved})` : "Approved" },
    { value: "rejected" as const, label: c ? `Rejected (${c.rejected})` : "Rejected" },
  ];

  const columns = useMemo(
    () => [
      helper.display({
        id: "incident",
        header: "Incident",
        cell: ({ row }) => (
          <div>
            <Link href={`/reviews/${row.original.incidentId}`} className="font-mono text-xs font-semibold hover:underline">
              {row.original.referenceCode}
            </Link>
            <p className="text-sm leading-snug font-semibold">{row.original.title}</p>
            <p className="mt-0.5 text-xs text-slate-600">
              {INCIDENT_TYPE_LABEL[row.original.incidentType]} · {row.original.locationText ?? "Location not stated"}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "priority",
        header: "Priority",
        cell: ({ row }) => <PriorityBadge priority={row.original.priority} short />,
      }),
      helper.display({
        id: "sources",
        header: "Sources",
        cell: ({ row }) => <span className="tnum text-sm">{row.original.sourceCount}</span>,
      }),
      helper.display({
        id: "missing",
        header: "Gaps",
        cell: ({ row }) =>
          row.original.missingInformationCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-sm">
              <span className="rounded border border-amber-400 bg-amber-50 px-1.5 py-px text-[10px] font-bold text-amber-800">GAP</span>
              <span className="tnum font-medium">{row.original.missingInformationCount}</span>
            </span>
          ) : (
            <span className="text-sm text-slate-600">None</span>
          ),
      }),
      helper.display({
        id: "confidence",
        header: "AI confidence",
        cell: ({ row }) => <ConfidenceBar value={row.original.extractionConfidence} />,
      }),
      helper.display({
        id: "risk",
        header: "Area risk",
        cell: ({ row }) => <RiskBadge level={row.original.riskLevel} />,
      }),
      helper.display({
        id: "state",
        header: "Status",
        cell: ({ row }) => (
          <div className="space-y-1">
            <ReviewStateBadge state={row.original.state} />
            {row.original.assignedTo ? <p className="text-xs text-slate-600">With {row.original.assignedTo}</p> : null}
          </div>
        ),
      }),
      helper.display({
        id: "received",
        header: "Received",
        cell: ({ row }) => <span className="tnum text-sm whitespace-nowrap">{formatRelative(row.original.receivedAt)}</span>,
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const open = row.original.state === "pending" || row.original.state === "needs_changes";
          return (
            <Button asChild variant={open ? "default" : "outline"} size="sm">
              <Link href={`/reviews/${row.original.incidentId}`}>
                {open ? "Review" : "View"}
                <span className="sr-only"> {row.original.referenceCode}</span>
              </Link>
            </Button>
          );
        },
      }),
    ],
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Review Queue"
        description="Candidates waiting for an editor's decision."
      />
      <ContextNote>AI confidence shows how well fields were extracted. Only an editor decision can approve a bulletin.</ContextNote>

      <SegmentedControl
        label="Review status"
        value={filters.tab}
        onChange={(v) => list.setFilter("tab", v)}
        options={tabs}
        className="max-w-full overflow-x-auto"
      />

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search reference, headline or place" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. SR-0412, Kadoma" className="lg:col-span-2" />
        <SelectField label="Priority" value={filters.priority} onChange={(v) => list.setFilter("priority", v)} options={PRIORITY_OPTIONS} allLabel="All priorities" />
      </FilterBar>

      <Card className="gap-0 overflow-hidden py-0">
        {reviews.error ? (
          <QueryError error={reviews.error} onRetry={reviews.refetch} />
        ) : (
          <DataTable
            caption="Incident candidates in the editorial queue"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(r) => r.incidentId}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["report", "reports"]}
            isLoading={reviews.isLoading}
            isFetching={reviews.isFetching}
            sort={list.sort}
            onSortChange={list.setSort}
            sortable={{
              priority: { key: "priority", firstDir: "desc" },
              sources: { key: "sources", firstDir: "desc" },
              missing: { key: "missing", firstDir: "desc" },
              received: { key: "received", firstDir: "desc" },
            }}
            rowHref={(r) => `/reviews/${r.incidentId}`}
            minWidth={1020}
            columnClassName={{ incident: "min-w-56", actions: "w-24" }}
            empty={
              <EmptyState
                title={filters.tab === "open" && !list.dirty ? "The queue is clear" : "Nothing matches"}
                description={
                  filters.tab === "open" && !list.dirty
                    ? "No incident candidates are waiting for an editor."
                    : "Try another status tab or clear the filters."
                }
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
