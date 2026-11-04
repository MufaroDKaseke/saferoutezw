"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PublicMapLazy } from "@/components/public/public-map-loader";
import type { PublicMapMarker } from "@/components/public/public-map";
import { Button } from "@/components/ui/button";
import {
  HAZARD_LABELS,
  PublicApiError,
  formatWhen,
  publicApi,
  type PublicBlackspotList,
  type PublicMapCollection,
} from "@/lib/public-api/client";

const SELECT =
  "h-11 w-full rounded-lg border border-input bg-white px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

type View = "map" | "list";

export function MapView() {
  const [hazard, setHazard] = useState("");
  const [severity, setSeverity] = useState("");
  const [days, setDays] = useState("");
  const [showAlerts, setShowAlerts] = useState(true);
  const [showBlackspots, setShowBlackspots] = useState(false);
  const [view, setView] = useState<View>("map");
  const filterKey = `${hazard}|${severity}|${days}`;
  // The outcome is stored with the filters it answers, so "loading" is derived (no setState in an effect).
  const [outcome, setOutcome] = useState<{ key: string; data: PublicMapCollection | null; error: string | null } | null>(null);
  const [blackspots, setBlackspots] = useState<PublicBlackspotList | null>(null);
  const [blackspotError, setBlackspotError] = useState<string | null>(null);
  const current = outcome?.key === filterKey ? outcome : null;
  const data = current?.data ?? null;
  const loading = current === null;
  const error = current?.error ?? blackspotError;

  useEffect(() => {
    const controller = new AbortController();
    publicApi
      .map(
        { hazard_type: hazard || undefined, severity: severity || undefined, since_days: days ? Number(days) : undefined },
        controller.signal,
      )
      .then((d) => setOutcome({ key: filterKey, data: d, error: null }))
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setOutcome({ key: filterKey, data: null, error: e instanceof PublicApiError ? e.message : "The map data could not be loaded." });
      });
    return () => controller.abort();
  }, [hazard, severity, days, filterKey]);

  useEffect(() => {
    if (!showBlackspots || blackspots) return;
    const controller = new AbortController();
    publicApi
      .blackspots(controller.signal)
      .then(setBlackspots)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setBlackspotError(e instanceof PublicApiError ? e.message : "Blackspots could not be loaded.");
      });
    return () => controller.abort();
  }, [showBlackspots, blackspots]);

  const markers = useMemo<PublicMapMarker[]>(() => {
    const out: PublicMapMarker[] = [];
    if (showAlerts && data) {
      for (const f of data.features) {
        out.push({
          id: f.properties.id,
          lng: f.geometry.coordinates[0],
          lat: f.geometry.coordinates[1],
          title: f.properties.title,
          subtitle: `${HAZARD_LABELS[f.properties.hazard_type] ?? f.properties.hazard_type} · ${formatWhen(f.properties.published_at)}`,
          href: f.properties.alert_url,
          kind: "alert",
          approximate: f.properties.location_precision !== "exact",
        });
      }
    }
    if (showBlackspots && blackspots) {
      for (const b of blackspots.items) {
        out.push({
          id: b.id,
          lat: b.latitude,
          lng: b.longitude,
          title: `Historical blackspot: ${b.name}`,
          subtitle: `Source: ${b.source_name}`,
          kind: "blackspot",
        });
      }
    }
    return out;
  }, [data, blackspots, showAlerts, showBlackspots]);

  return (
    <div className="space-y-4">
      <form className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-3" onSubmit={(e) => e.preventDefault()}>
        <label className="grid gap-1 text-sm font-medium">
          Hazard type
          <select className={SELECT} value={hazard} onChange={(e) => setHazard(e.target.value)}>
            <option value="">All types</option>
            {Object.entries(HAZARD_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Severity
          <select className={SELECT} value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">Any</option>
            <option value="minor">Minor</option>
            <option value="serious">Serious</option>
            <option value="fatal">Fatal</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Published
          <select className={SELECT} value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="">Any time</option>
            <option value="1">Last 24 hours</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
          </select>
        </label>
        <fieldset className="flex flex-wrap gap-x-6 gap-y-2 sm:col-span-3">
          <legend className="mb-1 text-sm font-medium">Layers</legend>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={showAlerts} onChange={(e) => setShowAlerts(e.target.checked)} />
            Published alerts
          </label>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={showBlackspots} onChange={(e) => setShowBlackspots(e.target.checked)} />
            Historical blackspots (past risk, not current alerts)
          </label>
        </fieldset>
      </form>

      <div className="flex gap-2" role="group" aria-label="View">
        <Button variant={view === "map" ? "default" : "outline"} size="lg" onClick={() => setView("map")} aria-pressed={view === "map"}>Map</Button>
        <Button variant={view === "list" ? "default" : "outline"} size="lg" onClick={() => setView("list")} aria-pressed={view === "list"}>List (low data)</Button>
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      ) : null}
      {loading ? <p className="text-sm text-slate-500" aria-live="polite">Loading…</p> : null}

      {data && data.unlocated_count > 0 ? (
        <p className="text-sm text-slate-600">
          {data.unlocated_count} published alert{data.unlocated_count === 1 ? " has" : "s have"} no reliable map position and
          are only in the <Link className="underline" href="/public/alerts">alert list</Link>.
        </p>
      ) : null}

      {view === "map" ? (
        <PublicMapLazy label="Map of published road alerts in Zimbabwe" className="h-[28rem] overflow-hidden rounded-xl" markers={markers} />
      ) : (
        <ul className="space-y-2">
          {markers.length === 0 && !loading ? (
            <li className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
              Nothing to show for these filters. This does not mean roads are free of hazards.
            </li>
          ) : null}
          {markers.map((m) => (
            <li key={`${m.kind}-${m.id}`} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <p className="font-medium">{m.href ? <Link className="underline" href={m.href}>{m.title}</Link> : m.title}</p>
              {m.subtitle ? <p className="text-slate-600">{m.subtitle}</p> : null}
              {m.approximate ? <p className="text-slate-500">Approximate location</p> : null}
            </li>
          ))}
        </ul>
      )}
      {data?.last_updated ? <p className="text-xs text-slate-500">Latest published notice: {formatWhen(data.last_updated)}</p> : null}
    </div>
  );
}
