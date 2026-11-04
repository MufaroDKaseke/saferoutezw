"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { RANGE_OPTIONS, SearchField, SelectField } from "@/components/shared/filters";
import { PageHeader } from "@/components/shared/page-header";
import { SimulationNote } from "@/components/shared/notes";
import { EmptyState, QueryError } from "@/components/shared/states";
import { ReviewStateBadge, RiskBadge, SeverityText } from "@/components/shared/status";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { getMapData } from "@/lib/api/incidents";
import type { DateRangeKey } from "@/lib/api/types";
import { SEVERITY_OPTIONS } from "@/lib/domain/constants";
import { credibilityLevel } from "@/lib/domain/derive";
import { formatRelative, formatShort } from "@/lib/formatters/date";
import { ACCURACY_LABEL, CREDIBILITY_LABEL, INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import { cn } from "@/lib/utils";
import type { Incident, Severity } from "@/types";
import { LayerToggles, MapLegend } from "./map-controls";
import { DEFAULT_LAYERS, markerKind, type MapLayers } from "./map-logic";
import { SafetyMap } from "./safety-map-loader";

export function MapView() {
  const [layers, setLayers] = useState<MapLayers>(DEFAULT_LAYERS);
  const [term, setTerm] = useState("");
  const [severity, setSeverity] = useState<Severity | undefined>();
  const [range, setRange] = useState<DateRangeKey | undefined>();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const search = useDebouncedValue(term);

  const query = { search, severity, range };
  const map = useResource(`map:${JSON.stringify(query)}`, () => getMapData(query));
  const data = map.data;
  const alertSet = useMemo(() => new Set(data?.alertIncidentIds ?? []), [data]);

  const visible = useMemo(
    () => (data?.incidents ?? []).filter((i) => layers[markerKind(i, alertSet)]),
    [data, layers, alertSet],
  );
  const selected = visible.find((i) => i.id === selectedId) ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Road Safety Map"
        description="Reported incidents and alerts against blackspots."
        actions={
          <Button variant="outline" size="lg" onClick={() => setPanelOpen((v) => !v)} aria-expanded={panelOpen} aria-controls="map-panel">
            {panelOpen ? <PanelRightClose aria-hidden /> : <PanelRightOpen aria-hidden />}
            {panelOpen ? "Hide intelligence panel" : "Show intelligence panel"}
          </Button>
        }
      />

      <SimulationNote>
        Internal editorial view. It includes unverified reports and must not be shown to the public. Rejected reports
        are never plotted.
        {getDataMode() === "mock" ? " Positions and blackspots are synthetic and illustrative." : ""}
      </SimulationNote>

      <LayerToggles layers={layers} onChange={setLayers} />

      <div className={cn("grid items-start gap-4", panelOpen && "lg:grid-cols-[minmax(0,1fr)_340px]")}>
        <Card className="gap-3 p-3">
          {map.error ? (
            <QueryError error={map.error} onRetry={map.refetch} />
          ) : !data ? (
            <Skeleton className="h-[620px] w-full rounded-xl" />
          ) : (
            <>
              <div className="h-[420px] sm:h-[560px] lg:h-[620px]">
                <SafetyMap
                  incidents={data.incidents}
                  alertIncidentIds={data.alertIncidentIds}
                  blackspots={data.blackspots}
                  layers={layers}
                  selectedId={selected?.id ?? null}
                  onSelect={setSelectedId}
                  className="h-full"
                />
              </div>
              <MapLegend inline className="px-1 pb-1" />
              <p className="px-1 text-xs text-slate-600">
                Map data © OpenStreetMap contributors. Dashed circles are historical risk context, not incidents.
              </p>
            </>
          )}
        </Card>

        {panelOpen ? (
          <aside id="map-panel" aria-label="Incident search and details" className="space-y-4">
            <Card className="gap-3">
              <div className="space-y-3 px-(--card-spacing)">
                <SearchField label="Search by place or incident" value={term} onChange={setTerm} placeholder="e.g. Rusape, Kadoma, A4" />
                <div className="grid grid-cols-2 gap-3">
                  <SelectField label="Severity" value={severity} onChange={setSeverity} options={SEVERITY_OPTIONS} allLabel="All" />
                  <SelectField label="Time range" value={range} onChange={setRange} options={RANGE_OPTIONS} allLabel="Any time" />
                </div>
              </div>
            </Card>

            <Card className="gap-0 py-0">
              <h2 className="border-b px-4 py-3 text-sm font-bold">
                Incidents <span className="font-normal text-slate-600">· {visible.length} shown</span>
              </h2>
              {!data ? (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : visible.length === 0 ? (
                <EmptyState title="Nothing to show" description="Turn a layer back on or widen the filters." />
              ) : (
                <ul className="max-h-80 divide-y overflow-y-auto">
                  {visible.map((i) => (
                    <li key={i.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(i.id)}
                        aria-pressed={i.id === selected?.id}
                        className={cn("block w-full px-4 py-3 text-left hover:bg-slate-50", i.id === selected?.id && "bg-slate-100")}
                      >
                        <span className="flex items-start justify-between gap-2">
                          <span className="text-sm leading-snug font-semibold">{i.title}</span>
                          <ReviewStateBadge state={i.reviewState} />
                        </span>
                        <span className="mt-0.5 block text-xs text-slate-600">{i.locationText ?? "Location not stated"}</span>
                        <span className="tnum mt-0.5 block text-xs text-slate-600">
                          {formatRelative(i.occurredAt ?? i.createdAt)} · <SeverityText severity={i.severity} />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <SelectedCard incident={selected} />
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function SelectedCard({ incident: i }: { incident: Incident | null }) {
  if (!i) {
    return (
      <Card>
        <p className="px-(--card-spacing) text-sm text-slate-600">Select a marker or an incident to see its details.</p>
      </Card>
    );
  }
  const level = credibilityLevel(i.credibilityScore);
  const open = i.reviewState === "pending" || i.reviewState === "needs_changes";
  return (
    <Card aria-live="polite">
      <div className="space-y-3 px-(--card-spacing)">
        <div className="flex items-center justify-between gap-2">
          <h2 className="section-label">Selected incident</h2>
          <span className="font-mono text-xs font-semibold">{i.referenceCode}</span>
        </div>
        <p className="text-lg leading-tight font-bold">{i.title}</p>
        <p className="text-sm text-slate-700">{i.locationText ?? "Location not stated"}</p>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-3 border-t pt-3 text-sm">
          <div>
            <dt className="section-label">Reported</dt>
            <dd className="tnum mt-0.5">{formatShort(i.createdAt)}</dd>
          </div>
          <div>
            <dt className="section-label">Type</dt>
            <dd className="mt-0.5">{INCIDENT_TYPE_LABEL[i.incidentType]}</dd>
          </div>
          <div>
            <dt className="section-label">Credibility</dt>
            <dd className="mt-0.5 font-semibold">{level ? CREDIBILITY_LABEL[level] : "Not assessed"}</dd>
          </div>
          <div>
            <dt className="section-label">Area risk</dt>
            <dd className="mt-0.5">
              <RiskBadge level={i.riskLevel} />
            </dd>
          </div>
        </dl>
        <p className="border-t pt-3 text-xs leading-relaxed text-slate-600">
          {i.point ? `${ACCURACY_LABEL[i.point.accuracy]} position (illustrative). ` : ""}
          Area risk is context. It does not show the event happened.
        </p>
        <Button asChild size="lg" className="w-full">
          <Link href={open ? `/reviews/${i.id}` : `/incidents/${i.id}`}>{open ? "Open in review workspace" : "Open incident"}</Link>
        </Button>
      </div>
    </Card>
  );
}

