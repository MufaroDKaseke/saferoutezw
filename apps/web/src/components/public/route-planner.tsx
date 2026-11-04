"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";
import { ArrowUpDown, Car, Check, ChevronDown, ChevronUp, Clock, Copy, Loader2, Map as MapIcon, Plus, Printer, Route as RouteIcon, Trash2 } from "lucide-react";
import { HazardTag, HazardTile, SeverityBadge } from "@/components/public/hazard";
import { PublicMapLazy } from "@/components/public/public-map-loader";
import type { PublicMapMarker } from "@/components/public/public-map";
import { ErrorNotice, Notice } from "@/components/public/site-chrome";
import { Button } from "@/components/ui/button";
import {
  PublicApiError,
  formatDuration,
  formatKm,
  formatWhen,
  publicApi,
  type RouteHazard,
  type RoutePlanResponse,
} from "@/lib/public-api/client";
import { BLACKSPOT } from "@/lib/public-api/hazard-style";
import { cn } from "@/lib/utils";

const MAX_STOPS = 5;

const FIELD =
  "h-12 w-full rounded-xl border border-input bg-white px-3.5 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

function HazardItem({ hazard }: { hazard: RouteHazard }) {
  return (
    <li>
      <Link
        href={hazard.alert_url}
        className="flex gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 hover:shadow-md"
      >
        <HazardTile hazardType={hazard.hazard_type} severity={hazard.severity} />
        <span className="min-w-0 space-y-1.5 text-sm">
          <span className="flex flex-wrap items-center gap-2">
            {hazard.severity !== "unknown" ? <SeverityBadge severity={hazard.severity} /> : null}
            <HazardTag hazardType={hazard.hazard_type} />
          </span>
          <span className="block text-[15px] font-bold text-slate-900 underline-offset-2 hover:underline">{hazard.headline}</span>
          <span className="block text-slate-600">
            About {Math.round(hazard.distance_from_route_m)} m from the route ·{" "}
            {hazard.location_precision === "exact" ? "exact position" : "approximate position"}
          </span>
          <span className="block text-[13px] text-slate-500">
            {hazard.source_names.length ? `Source: ${hazard.source_names.join(", ")} · ` : ""}Updated {formatWhen(hazard.updated_at)}
          </span>
        </span>
      </Link>
    </li>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <p className="text-2xl font-extrabold tracking-tight text-slate-900 tnum">{value}</p>
      <p className="text-[13px] text-slate-600">{label}</p>
    </div>
  );
}

export function RoutePlanner({ operator = false }: { operator?: boolean }) {
  const params = useSearchParams();
  const uid = useId();
  const [origin, setOrigin] = useState(params.get("from") ?? "");
  const [destination, setDestination] = useState(params.get("to") ?? "");
  const [stops, setStops] = useState<string[]>([]);
  const [result, setResult] = useState<RoutePlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await publicApi.planRoute({
        origin: { query: origin.trim() },
        destination: { query: destination.trim() },
        stops: stops.map((s) => s.trim()).filter(Boolean).map((query) => ({ query })),
        mode: "drive",
        // Stop optimisation is not available yet: stops always stay in the order given.
        optimise: false,
      });
      setResult(response);
      queueMicrotask(() => resultRef.current?.focus());
    } catch (e) {
      setError(e instanceof PublicApiError ? e.message : "The route could not be planned.");
    } finally {
      setBusy(false);
    }
  }

  const markers = useMemo<PublicMapMarker[]>(() => {
    if (!result) return [];
    return [
      ...result.places.map((p, i) => ({
        id: `p${i}`, lat: p.latitude, lng: p.longitude, title: p.label, kind: "stop" as const,
      })),
      ...result.blackspots.map((b) => ({
        id: b.id, lat: b.latitude, lng: b.longitude, title: `Historical blackspot: ${b.name}`,
        subtitle: `Source: ${b.source_name}`, kind: "blackspot" as const,
      })),
    ];
  }, [result]);

  const summaryText = result
    ? [
        `SafeRouteZW journey: ${result.places.map((p) => p.label).join(" > ")}`,
        `${formatKm(result.distance_m)}, about ${formatDuration(result.duration_s)} (engine estimate, no live traffic).`,
        result.hazards.length
          ? `Published alerts near the route: ${result.hazards.map((h) => h.headline).join("; ")}.`
          : "No published alerts were found near the route (this does not mean it is safe).",
        result.blackspots.length ? `Historical blackspots: ${result.blackspots.map((b) => b.name).join("; ")}.` : "",
        `Data updated: ${result.data_updated_at ? formatWhen(result.data_updated_at) : "no published alerts yet"}.`,
      ].filter(Boolean).join("\n")
    : "";

  async function copy() {
    try {
      await navigator.clipboard.writeText(summaryText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copying is not available in this browser. Use Print instead.");
    }
  }

  function swap() {
    setOrigin(destination);
    setDestination(origin);
  }

  const move = (i: number, dir: -1 | 1) =>
    setStops((list) => {
      const j = i + dir;
      if (j < 0 || j >= list.length) return list;
      const next = [...list];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const originField = (
    <label className="grid gap-1.5 text-sm font-semibold">
      From
      <input value={origin} onChange={(e) => setOrigin(e.target.value)} required minLength={2} maxLength={200} className={FIELD} placeholder="Town, place or address" autoComplete="off" />
    </label>
  );
  const destinationField = (
    <label className="grid gap-1.5 text-sm font-semibold">
      To
      <input value={destination} onChange={(e) => setDestination(e.target.value)} required minLength={2} maxLength={200} className={FIELD} placeholder="Town, place or address" autoComplete="off" />
    </label>
  );
  const swapButton = (
    <Button type="button" variant="outline" size="icon-lg" aria-label="Swap From and To" onClick={swap} className="rounded-full shadow-sm">
      <ArrowUpDown className="size-4" />
    </Button>
  );
  const submitButton = (
    <Button type="submit" variant="approve" size="lg" disabled={busy} className="h-12 px-6 text-base" aria-describedby={`${uid}-note`}>
      {busy ? <Loader2 className="size-5 animate-spin" /> : <RouteIcon className="size-5" />}
      {busy ? "Planning…" : operator ? "Plan trip" : "Plan route"}
    </Button>
  );
  const modeNote = (
    <p id={`${uid}-note`} className="flex items-start gap-2 text-[13px] leading-snug text-slate-600">
      <Car className="mt-0.5 size-4 shrink-0" aria-hidden />
      Driving (car or light vehicle). Truck height, weight and clearance rules are not checked.
    </p>
  );

  const form = operator ? (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5 print:hidden">
      <h2 className="text-lg font-bold text-slate-900">Your trip</h2>
      {originField}
      <div className="space-y-2.5">
        <p className="text-sm font-semibold">
          Stops in order <span className="font-normal text-slate-600">(up to {MAX_STOPS})</span>
        </p>
        {stops.length === 0 ? <p className="text-sm text-slate-600">No stops yet. Add a stop to plan a multi-stop trip.</p> : null}
        <ol className="space-y-2.5">
          {stops.map((stop, i) => (
            <li key={i} className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-2.5">
              <div className="flex items-center gap-2">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-emerald-700 text-[13px] font-bold text-white" aria-hidden>
                  {i + 1}
                </span>
                <input
                  value={stop}
                  maxLength={200}
                  aria-label={`Stop ${i + 1}`}
                  className={cn(FIELD, "h-11")}
                  placeholder="Town, place or address"
                  onChange={(e) => setStops(stops.map((s, j) => (j === i ? e.target.value : s)))}
                />
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="lg" className="flex-1" disabled={i === 0} aria-label={`Move stop ${i + 1} up`} onClick={() => move(i, -1)}>
                  <ChevronUp /> Up
                </Button>
                <Button type="button" variant="outline" size="lg" className="flex-1" disabled={i === stops.length - 1} aria-label={`Move stop ${i + 1} down`} onClick={() => move(i, 1)}>
                  <ChevronDown /> Down
                </Button>
                <Button type="button" variant="reject" size="icon-lg" aria-label={`Remove stop ${i + 1}`} onClick={() => setStops(stops.filter((_, j) => j !== i))}>
                  <Trash2 />
                </Button>
              </div>
            </li>
          ))}
        </ol>
        {stops.length < MAX_STOPS ? (
          <Button type="button" variant="outline" size="lg" className="w-full sm:w-auto" onClick={() => setStops([...stops, ""])}>
            <Plus /> Add stop ({stops.length}/{MAX_STOPS})
          </Button>
        ) : null}
      </div>
      {destinationField}
      {modeNote}
      <p className="text-[13px] text-slate-600">Stop order optimisation is not available yet. Stops stay in the order you set.</p>
      <div className="flex gap-3">
        {submitButton}
        {swapButton}
      </div>
    </form>
  ) : (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5 print:hidden">
      <div className="grid items-end gap-3 md:grid-cols-[1fr_auto_1fr_auto]">
        {originField}
        <div className="flex justify-center md:pb-0.5">{swapButton}</div>
        {destinationField}
        {submitButton}
      </div>
      {modeNote}
    </form>
  );

  const resultBlock = (
    <div ref={resultRef} tabIndex={-1} className="space-y-5 outline-none" aria-live="polite">
      {result ? (
        <>
          <section aria-labelledby="summary" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
            <div>
              <h2 id="summary" className="text-sm font-semibold text-slate-600">
                Route summary
              </h2>
              <p className="mt-1 text-xl leading-snug font-extrabold tracking-tight text-slate-900">{result.places.map((p) => p.label).join(" → ")}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Stat value={formatKm(result.distance_m)} label="Estimated distance" />
              <Stat value={formatDuration(result.duration_s)} label="Estimated driving time" />
              <Stat value={String(result.hazards.length)} label={result.hazards.length === 1 ? "Published alert" : "Published alerts"} />
              <Stat value={String(result.blackspots.length)} label={result.blackspots.length === 1 ? "Historical blackspot" : "Historical blackspots"} />
            </div>
            <p className="flex items-start gap-1.5 text-[13px] text-slate-600">
              <Clock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>
                {result.duration_note} Alerts are matched within {Math.round(result.hazard_buffer_m)} m of the route.{" "}
                {result.data_updated_at ? `Alerts last updated ${formatWhen(result.data_updated_at)}.` : "No alerts have been published yet."}
              </span>
            </p>
            {result.provider === "mock" ? (
              <Notice tone="warning">Demonstration route: a straight line, not a road route.</Notice>
            ) : null}
            <div className="flex flex-wrap gap-2 print:hidden">
              <Button asChild size="lg" variant="outline">
                <a href="#route-map">
                  <MapIcon /> Show map
                </a>
              </Button>
              <Button size="lg" variant="outline" onClick={copy}>
                {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy summary"}
              </Button>
              {operator ? (
                <Button size="lg" variant="approve" onClick={() => window.print()}>
                  <Printer /> Print driver briefing
                </Button>
              ) : null}
            </div>
          </section>

          <section aria-labelledby="hz" className="space-y-3">
            <h2 id="hz" className="text-lg font-extrabold tracking-tight text-slate-900">
              Published alerts near this route <span className="font-semibold text-slate-500">({result.hazards.length})</span>
            </h2>
            {result.hazards.length ? (
              <ul className="space-y-3">{result.hazards.map((h) => <HazardItem key={h.alert_id} hazard={h} />)}</ul>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-700">None found. This does not mean the road is safe.</p>
            )}
          </section>

          {result.closures.length ? (
            <section aria-labelledby="cl" className="space-y-3">
              <h2 id="cl" className="text-lg font-extrabold tracking-tight text-slate-900">
                Published road closures <span className="font-semibold text-slate-500">({result.closures.length})</span>
              </h2>
              <ul className="space-y-3">{result.closures.map((h) => <HazardItem key={h.alert_id} hazard={h} />)}</ul>
              <p className="text-xs text-slate-500">The route is not changed automatically to avoid closures.</p>
            </section>
          ) : null}

          <section aria-labelledby="bs" className="space-y-3">
            <h2 id="bs" className="text-lg font-extrabold tracking-tight text-slate-900">
              Historical blackspots <span className="font-semibold text-slate-500">({result.blackspots.length})</span>
            </h2>
            <p className="text-sm text-slate-600">Places with past incidents. They describe past risk, not current alerts.</p>
            {result.blackspots.length ? (
              <ul className="space-y-3">
                {result.blackspots.map((b) => (
                  <li key={b.id} className={cn("flex gap-3 rounded-2xl border-2 p-4 text-sm", BLACKSPOT.card)}>
                    <HazardTile hazardType="blackspot" blackspot />
                    <div className="space-y-1">
                      <span className="inline-flex h-7 items-center rounded-lg bg-indigo-100 px-2.5 text-[12.5px] font-semibold text-indigo-900">Historical blackspot</span>
                      <p className="text-[15px] font-bold text-slate-900">{b.name}</p>
                      <p className="text-slate-700">About {Math.round(b.distance_from_route_m)} m from the route · Source: {b.source_name}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-700">No recorded blackspots near this route in our sourced data.</p>
            )}
          </section>

          {result.warnings.length ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
              {result.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          ) : null}
          <Notice tone="warning" role="note">{result.disclaimer}</Notice>

        </>
      ) : null}
    </div>
  );

  return (
    <div className={cn("gap-6", operator ? "grid lg:grid-cols-[24rem_minmax(0,1fr)] lg:items-start" : "space-y-6")}>
      <div className={operator ? "lg:sticky lg:top-20 print:static" : undefined}>{form}</div>
      <div className="min-w-0 space-y-5">
        {error ? <ErrorNotice title="The route could not be planned." message={error} /> : null}
        {busy ? (
          <p role="status" className="flex items-center gap-2 rounded-xl bg-white p-4 text-sm font-medium text-slate-700 ring-1 ring-slate-200">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Finding the route and checking published alerts…
          </p>
        ) : null}
        {result ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:items-start print:block">
            {resultBlock}
            <div id="route-map" className="scroll-mt-20 space-y-2 lg:sticky lg:top-20 print:hidden">
              <h2 className="text-lg font-extrabold tracking-tight text-slate-900 lg:sr-only">Route map</h2>
              <PublicMapLazy label="Map of your route" className="h-80 overflow-hidden rounded-2xl ring-1 ring-slate-200 lg:h-[34rem]" route={result.geometry as { type: string; coordinates: unknown }} markers={markers} />
              <p className="text-xs text-slate-500">Hazards are listed with the route summary. Historical blackspots show on the map as dashed rings.</p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
