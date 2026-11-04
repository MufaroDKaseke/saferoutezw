"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, RANGE_OPTIONS, SearchField, SelectField } from "@/components/shared/filters";
import { SegmentMeter } from "@/components/shared/meter";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote } from "@/components/shared/notes";
import { EmptyState, QueryError } from "@/components/shared/states";
import { ReviewStateBadge, RiskBadge, SeverityText, VerificationBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { listIncidents } from "@/lib/api/incidents";
import type { DateRangeKey } from "@/lib/api/types";
import {
  INCIDENT_TYPE_OPTIONS,
  PROVINCE_OPTIONS,
  REVIEW_STATE_OPTIONS,
  SEVERITY_OPTIONS,
  VERIFICATION_OPTIONS,
} from "@/lib/domain/constants";
import { credibilityLevel, scoreSegments } from "@/lib/domain/derive";
import { formatShort } from "@/lib/formatters/date";
import { CREDIBILITY_LABEL, INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import type { Incident, IncidentType, Province, ReviewState, Severity, VerificationState } from "@/types";

const helper = columnHelper<Incident>();
const PAGE_SIZE = 10;

export function IncidentsView() {
  const list = useListState(
    {
      search: "",
      reviewState: undefined as ReviewState | undefined,
      type: undefined as IncidentType | undefined,
      province: undefined as Province | undefined,
      range: undefined as DateRangeKey | undefined,
      severity: undefined as Severity | undefined,
      verification: undefined as VerificationState | undefined,
    },
    { id: "createdAt", dir: "desc" },
  );
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const query = {
    search,
    reviewState: filters.reviewState,
    type: filters.type,
    province: filters.province,
    range: filters.range,
    severity: filters.severity,
    verification: filters.verification,
    page: list.page,
    pageSize: PAGE_SIZE,
    sort: list.sort?.id,
    dir: list.sort?.dir,
  };
  const incidents = useResource(`incidents:${JSON.stringify(query)}`, () => listIncidents(query));
  const data = incidents.data;

  const columns = useMemo(
    () => [
      helper.display({
        id: "incident",
        header: "Incident",
        cell: ({ row }) => (
          <div className="min-w-0">
            <Link href={`/incidents/${row.original.id}`} className="font-mono text-xs font-semibold hover:underline">
              {row.original.referenceCode}
            </Link>
            <p className="text-sm leading-snug font-semibold">{row.original.title}</p>
            <p className="mt-0.5 text-xs text-slate-600">{INCIDENT_TYPE_LABEL[row.original.incidentType]}</p>
          </div>
        ),
      }),
      helper.display({
        id: "location",
        header: "Reported location",
        cell: ({ row }) => (
          <div className="text-sm">
            <p className="leading-snug">{row.original.locationText ?? "Not stated"}</p>
            {row.original.province ? <p className="text-xs text-slate-600">{row.original.province}</p> : null}
          </div>
        ),
      }),
      helper.display({
        id: "time",
        header: "Event time",
        cell: ({ row }) => (
          <div className="tnum text-sm">
            <p>{row.original.occurredAt ? formatShort(row.original.occurredAt) : "Not stated"}</p>
            <p className="text-xs text-slate-600">Reported {formatShort(row.original.createdAt)}</p>
          </div>
        ),
      }),
      helper.display({
        id: "severity",
        header: "Severity",
        cell: ({ row }) => <SeverityText severity={row.original.severity} prefix={false} />,
      }),
      helper.display({
        id: "sources",
        header: "Sources",
        cell: ({ row }) => (
          <span className="tnum text-sm">
            {row.original.sourceCount} {row.original.sourceCount === 1 ? "article" : "articles"}
          </span>
        ),
      }),
      helper.display({
        id: "credibility",
        header: "Credibility",
        cell: ({ row }) => {
          const level = credibilityLevel(row.original.credibilityScore);
          if (!level) return <span className="text-sm text-slate-600">Not assessed</span>;
          return (
            <div className="w-24 space-y-1.5">
              <span className="text-sm font-medium">{CREDIBILITY_LABEL[level]}</span>
              <SegmentMeter filled={scoreSegments(row.original.credibilityScore)} label="Credibility" />
            </div>
          );
        },
      }),
      helper.display({
        id: "risk",
        header: "Area risk",
        cell: ({ row }) => <RiskBadge level={row.original.riskLevel} />,
      }),
      helper.display({
        id: "state",
        header: "Review",
        cell: ({ row }) => (
          <div className="space-y-1">
            <ReviewStateBadge state={row.original.reviewState} />
            <div>
              <VerificationBadge state={row.original.verification} short />
            </div>
          </div>
        ),
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <Button asChild variant="outline" size="icon" title="Open incident">
            <Link href={`/incidents/${row.original.id}`} aria-label={`Open ${row.original.referenceCode}`}>
              <ArrowRight aria-hidden />
            </Link>
          </Button>
        ),
      }),
    ],
    [],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Incident Intelligence"
        description="Incident candidates extracted from articles. Several articles can support one incident, and one article can describe several. None is confirmed until an editor decides."
      />
      <ContextNote>
        Credibility and area risk are separate. Credibility is how well the evidence supports the event. Area risk is
        historical context for the place, and it never proves a new incident happened.
      </ContextNote>

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search reference, road or place" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. SR-0412, Rusape, A5" className="lg:col-span-2" />
        <SelectField label="Review status" value={filters.reviewState} onChange={(v) => list.setFilter("reviewState", v)} options={REVIEW_STATE_OPTIONS} allLabel="All statuses" />
        <SelectField label="Incident type" value={filters.type} onChange={(v) => list.setFilter("type", v)} options={INCIDENT_TYPE_OPTIONS} allLabel="All types" />
        <SelectField label="Province or city" value={filters.province} onChange={(v) => list.setFilter("province", v)} options={PROVINCE_OPTIONS} allLabel="All provinces" />
        <SelectField label="Date range" value={filters.range} onChange={(v) => list.setFilter("range", v)} options={RANGE_OPTIONS} allLabel="Any time" />
        <SelectField label="Severity" value={filters.severity} onChange={(v) => list.setFilter("severity", v)} options={SEVERITY_OPTIONS} allLabel="All severities" />
        <SelectField label="Verification" value={filters.verification} onChange={(v) => list.setFilter("verification", v)} options={VERIFICATION_OPTIONS} allLabel="All" />
      </FilterBar>

      <Card className="gap-0 overflow-hidden py-0">
        {incidents.error ? (
          <QueryError error={incidents.error} onRetry={incidents.refetch} />
        ) : (
          <DataTable
            caption="Incident candidates"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(i) => i.id}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["incident", "incidents"]}
            isLoading={incidents.isLoading}
            isFetching={incidents.isFetching}
            sort={list.sort}
            onSortChange={list.setSort}
            sortable={{
              time: { key: "occurredAt", firstDir: "desc" },
              severity: { key: "severity", firstDir: "desc" },
              sources: { key: "sources", firstDir: "desc" },
              risk: { key: "risk", firstDir: "desc" },
            }}
            rowHref={(i) => `/incidents/${i.id}`}
            minWidth={980}
            columnClassName={{ incident: "min-w-44", location: "min-w-40", actions: "w-14" }}
            empty={
              <EmptyState
                title="No incidents match these filters"
                description="Try widening the date range or clearing a filter."
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
