"use client";

import { useMemo, useState } from "react";
import { MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MapLegend } from "@/components/maps/map-controls";
import { SafetyMap } from "@/components/maps/safety-map-loader";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, SearchField, SelectField } from "@/components/shared/filters";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote, SimulationNote } from "@/components/shared/notes";
import { EmptyState, QueryError } from "@/components/shared/states";
import { RiskBadge, SyntheticBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { listBlackspots } from "@/lib/api/blackspots";
import { PROVINCE_OPTIONS, RISK_OPTIONS } from "@/lib/domain/constants";
import { formatDay } from "@/lib/formatters/date";
import type { Blackspot, Province, RiskLevel } from "@/types";

const helper = columnHelper<Blackspot>();
const NO_INCIDENTS: never[] = [];
const MAP_LAYERS = { reported: false, reviewed: false, approved: false, blackspots: true, clusters: false } as const;

function year(iso: string | null) {
  if (!iso) return "?";
  return formatDay(iso).length ? new Date(iso).getUTCFullYear() : "";
}

export function BlackspotsView() {
  const list = useListState({
    search: "",
    risk: undefined as RiskLevel | undefined,
    province: undefined as Province | undefined,
  });
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const query = { search, risk: filters.risk, province: filters.province };
  const spots = useResource(`blackspots:${JSON.stringify(query)}`, () => listBlackspots(query));
  const data = spots.data;

  const columns = useMemo(
    () => [
      helper.display({
        id: "code",
        header: "Reference",
        cell: ({ row }) => (
          <button
            type="button"
            onClick={() => setSelectedId(row.original.id)}
            className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold hover:underline"
            aria-label={`Show ${row.original.code} on the map`}
          >
            <MapPin className="size-3.5" aria-hidden />
            {row.original.code}
          </button>
        ),
      }),
      helper.display({
        id: "place",
        header: "Road and location",
        cell: ({ row }) => (
          <div>
            <p className="text-sm font-semibold">{row.original.roadName ?? row.original.name}</p>
            <p className="text-xs text-slate-600">
              {row.original.roadName ? row.original.name : "Location from the source dataset"}
              {row.original.province ? ` · ${row.original.province}` : ""}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "risk",
        header: "Historical risk",
        cell: ({ row }) => <RiskBadge level={row.original.riskLevel} />,
      }),
      helper.display({
        id: "period",
        header: "Observation period",
        cell: ({ row }) => (
          <span className="tnum text-sm">
            {year(row.original.observationPeriod.from)}–{year(row.original.observationPeriod.to)}
          </span>
        ),
      }),
      helper.display({
        id: "source",
        header: "Data source",
        cell: ({ row }) => (
          <div className="text-sm">
            <p className="flex items-center gap-2">
              {row.original.dataSourceName}
              {row.original.synthetic ? <SyntheticBadge /> : null}
            </p>
            <p className="font-mono text-xs text-slate-600">{row.original.sourceReference}</p>
          </div>
        ),
      }),
      helper.display({
        id: "nearby",
        header: "Candidates within 25 km",
        cell: ({ row }) => <span className="tnum text-sm font-medium">{row.original.nearbyIncidentCount}</span>,
      }),
    ],
    [],
  );

  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Historical Blackspots"
        description="Places with a history of road crashes. This is background risk, kept apart from the live incident feed."
      />
      {getDataMode() === "mock" ? (
        <SimulationNote>
          Every blackspot here is <strong>synthetic</strong>. Positions are illustrative and none is an official record.
          Verified datasets are loaded through the backend, not the browser.
        </SimulationNote>
      ) : null}
      <ContextNote>
        A blackspot near a report is context only. It never proves that the reported accident happened.
      </ContextNote>

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search by road or location" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="e.g. A3, Kadoma, Chitungwiza" className="lg:col-span-2" />
        <SelectField label="Risk level" value={filters.risk} onChange={(v) => list.setFilter("risk", v)} options={RISK_OPTIONS} allLabel="All levels" />
        <SelectField label="Province" value={filters.province} onChange={(v) => list.setFilter("province", v)} options={PROVINCE_OPTIONS} allLabel="All provinces" />
      </FilterBar>

      {spots.error ? (
        <Card>
          <QueryError error={spots.error} onRetry={spots.refetch} />
        </Card>
      ) : (
        <div className="grid items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card className="gap-3 p-3 2xl:order-2">
            <div className="h-[420px]">
              {data ? (
                <SafetyMap
                  incidents={NO_INCIDENTS}
                  blackspots={data.items}
                  layers={{ ...MAP_LAYERS }}
                  selectedBlackspotId={selectedId}
                  onSelectBlackspot={setSelectedId}
                  label="Map of historical road blackspots in Zimbabwe"
                  className="h-full"
                />
              ) : (
                <div className="h-full animate-pulse rounded-xl bg-slate-100" />
              )}
            </div>
            <MapLegend inline className="px-1 pb-1" />
          </Card>

          <Card className="gap-0 overflow-hidden py-0 2xl:order-1">
            <DataTable
              caption="Historical blackspots"
              columns={columns}
              data={data?.items ?? []}
              getRowId={(b) => b.id}
              total={total}
              page={1}
              pageSize={50}
              onPageChange={() => {}}
              noun={["blackspot", "blackspots"]}
              isLoading={spots.isLoading}
              isFetching={spots.isFetching}
              minWidth={820}
              empty={
                list.dirty ? (
                  <EmptyState
                    title="No blackspots match these filters"
                    description="Try another road, province or risk level."
                    action={<Button variant="outline" onClick={list.reset}>Clear filters</Button>}
                  />
                ) : (
                  <EmptyState
                    title="No verified blackspot data loaded"
                    description="Historical blackspot records come from an official or academic dataset. None has been loaded yet."
                  />
                )
              }
            />
          </Card>
        </div>
      )}
    </div>
  );
}
