"use client";

import Link from "next/link";
import { useMemo } from "react";
import { BellRing, CheckCheck, Clock, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, SearchField, SelectField } from "@/components/shared/filters";
import { KpiCard, KpiCardSkeleton } from "@/components/shared/kpi-card";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote, SimulationNote } from "@/components/shared/notes";
import { EmptyState, QueryError } from "@/components/shared/states";
import { AlertStateBadge, ChannelStatusBadge, SyntheticBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { listAlerts } from "@/lib/api/alerts";
import { getReviewCounts } from "@/lib/api/reviews";
import { getDataMode } from "@/lib/api/config";
import { formatShort } from "@/lib/formatters/date";
import { ALERT_STATE_LABEL, CHANNEL_LABEL, INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import type { AlertPublicationState, ChannelKind, PublicAlert } from "@/types";

const helper = columnHelper<PublicAlert>();
const PAGE_SIZE = 10;

const STATE_OPTIONS = (Object.keys(ALERT_STATE_LABEL) as AlertPublicationState[]).map((value) => ({ value, label: ALERT_STATE_LABEL[value] }));
const CHANNEL_OPTIONS = (["whatsapp", "sms", "web"] as ChannelKind[]).map((value) => ({ value, label: CHANNEL_LABEL[value] }));

export function AlertsView() {
  const list = useListState({
    search: "",
    state: undefined as AlertPublicationState | undefined,
    channel: undefined as ChannelKind | undefined,
  });
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const query = { search, state: filters.state, channel: filters.channel, page: list.page, pageSize: PAGE_SIZE };
  const alerts = useResource(`alerts:${JSON.stringify(query)}`, () => listAlerts(query));
  const all = useResource("alerts:all", () => listAlerts({ pageSize: 100 }));
  const waiting = useResource("alerts:awaiting", () => getReviewCounts());
  const data = alerts.data;

  const stats = useMemo(() => {
    const items = all.data?.items ?? [];
    const channels = items.flatMap((a) => a.channels);
    return {
      approved: items.length,
      live: channels.filter((c) => c.status === "sent").length,
      total: channels.length,
      failures: items.filter((a) => a.channels.some((c) => c.status === "failed")),
    };
  }, [all.data]);

  const columns = useMemo(
    () => [
      helper.display({
        id: "reference",
        header: "Alert",
        cell: ({ row }) => (
          <div>
            <Link href={`/alerts/${row.original.id}`} className="font-mono text-xs font-semibold hover:underline">
              {row.original.reference}
            </Link>
            <p className="text-xs whitespace-nowrap text-slate-600">from {row.original.incidentReference}</p>
          </div>
        ),
      }),
      helper.display({
        id: "headline",
        header: "Headline",
        cell: ({ row }) => (
          <div>
            <p className="flex items-center gap-2 text-sm leading-snug font-semibold">
              {row.original.headline}
              {row.original.synthetic ? <SyntheticBadge /> : null}
            </p>
            <p className="mt-0.5 text-xs text-slate-600">
              {INCIDENT_TYPE_LABEL[row.original.incidentType]} · {row.original.locationText ?? "Location not stated"}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "approved",
        header: "Approved by",
        cell: ({ row }) => (
          <div className="tnum text-sm">
            <p>{formatShort(row.original.approvedAt)}</p>
            <p className="text-xs text-slate-600">by {row.original.approvedByName}</p>
          </div>
        ),
      }),
      helper.display({
        id: "state",
        header: "Publication status",
        cell: ({ row }) => (
          <div className="space-y-1">
            <AlertStateBadge state={row.original.publicationState} />
            {row.original.publishedAt ? <p className="tnum text-xs text-slate-600">Sent {formatShort(row.original.publishedAt)}</p> : null}
          </div>
        ),
      }),
      helper.display({
        id: "channels",
        header: "Distribution channels",
        cell: ({ row }) =>
          row.original.channels.length === 0 ? (
            <span className="text-sm text-slate-600">None yet. Not sent.</span>
          ) : (
            <ul className="space-y-1">
              {row.original.channels.map((c) => (
                <li key={c.channel} className="flex items-center gap-2 text-xs">
                  <span className="w-28 shrink-0 whitespace-nowrap text-slate-700">{c.channel === "web" ? "Map and API" : CHANNEL_LABEL[c.channel]}</span>
                  <ChannelStatusBadge status={c.status} channel={c.channel} />
                  <span className="tnum whitespace-nowrap text-slate-600">
                    {c.attempts.length} of {c.maxAttempts}
                  </span>
                </li>
              ))}
            </ul>
          ),
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <Button asChild variant="outline" size="sm">
            <Link href={`/alerts/${row.original.id}`}>
              Open<span className="sr-only"> {row.original.reference}</span>
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
        title="Public Alert Management"
        description="Every alert here was approved by a named human editor. Track where each bulletin went and retry anything that failed."
      />
      {getDataMode() === "mock" ? (
        <SimulationNote>
          Simulation. Nothing is really sent to WhatsApp, SMS or any API. Retries and publishing change the demo only.
        </SimulationNote>
      ) : null}

      <section aria-label="Alert summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {!all.data ? (
          Array.from({ length: 4 }, (_, i) => <KpiCardSkeleton key={i} />)
        ) : (
          <>
            <KpiCard title="Approved alerts" value={stats.approved} icon={CheckCheck} tone="emerald" hint="Each signed off by a named editor" />
            <KpiCard title="Channels live" value={`${stats.live} of ${stats.total}`} icon={BellRing} hint="Delivered or live across alerts" />
            <KpiCard
              title="Delivery failures"
              value={stats.failures.length}
              icon={TriangleAlert}
              tone={stats.failures.length ? "red" : "slate"}
              emphasis={stats.failures.length > 0}
              hint={stats.failures.length ? <strong className="text-red-800">{stats.failures.map((a) => a.reference).join(", ")}</strong> : "None"}
            />
            <KpiCard
              title="Cannot be sent yet"
              value={waiting.data ? waiting.data.pending + waiting.data.needs_changes : "–"}
              icon={Clock}
              tone="amber"
              hint={
                waiting.data ? (
                  <>
                    <strong className="text-emerald-800">Awaiting human approval</strong> · {waiting.data.pending} pending,{" "}
                    {waiting.data.needs_changes} needs changes
                  </>
                ) : (
                  <strong className="text-emerald-800">Awaiting human approval</strong>
                )
              }
              href="/reviews"
            />
          </>
        )}
      </section>

      <ContextNote>Approved does not mean delivered. Each channel records its own attempts and result.</ContextNote>

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search reference, headline or place" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. A-0408, Gweru" className="lg:col-span-2" />
        <SelectField label="Status" value={filters.state} onChange={(v) => list.setFilter("state", v)} options={STATE_OPTIONS} allLabel="All statuses" />
        <SelectField label="Channel" value={filters.channel} onChange={(v) => list.setFilter("channel", v)} options={CHANNEL_OPTIONS} allLabel="All channels" />
      </FilterBar>

      <Card className="gap-0 overflow-hidden py-0">
        {alerts.error ? (
          <QueryError error={alerts.error} onRetry={alerts.refetch} />
        ) : (
          <DataTable
            caption="Approved public alerts"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(a) => a.id}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["alert", "alerts"]}
            isLoading={alerts.isLoading}
            isFetching={alerts.isFetching}
            rowHref={(a) => `/alerts/${a.id}`}
            minWidth={1000}
            columnClassName={{ headline: "min-w-56", channels: "min-w-64" }}
            empty={
              <EmptyState
                title="No alerts yet"
                description="An alert appears here only after an editor approves a bulletin in the review queue."
                action={
                  <Button asChild variant="outline">
                    <Link href="/reviews">Open review queue</Link>
                  </Button>
                }
              />
            }
          />
        )}
      </Card>
    </div>
  );
}
