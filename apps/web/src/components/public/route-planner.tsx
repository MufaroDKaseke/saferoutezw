"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { Copy, Plus, Printer, Trash2 } from "lucide-react";
import { PublicMapLazy } from "@/components/public/public-map-loader";
import type { PublicMapMarker } from "@/components/public/public-map";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  HAZARD_LABELS,
  PublicApiError,
  formatDuration,
  formatKm,
  formatWhen,
  publicApi,
  type RouteHazard,
  type RoutePlanResponse,
} from "@/lib/public-api/client";

const MAX_STOPS = 5;
const SELECT =
  "h-11 w-full rounded-lg border border-input bg-white px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

function HazardItem({ hazard }: { hazard: RouteHazard }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <p className="font-medium">
        <Link className="underline" href={hazard.alert_url}>{hazard.headline}</Link>
      </p>
      <p className="text-slate-600">
        {HAZARD_LABELS[hazard.hazard_type] ?? hazard.hazard_type} · about {Math.round(hazard.distance_from_route_m)} m from the route ·{" "}
        {hazard.location_precision === "exact" ? "exact position" : "approximate position"}
      </p>
      <p className="text-slate-500">
        {hazard.source_names.length ? `Source: ${hazard.source_names.join(", ")} · ` : ""}Updated {formatWhen(hazard.updated_at)}
      </p>
    </li>
  );
}

export function RoutePlanner({ operator = false }: { operator?: boolean }) {
  const params = useSearchParams();
  const [origin, setOrigin] = useState(params.get("from") ?? "");
  const [destination, setDestination] = useState(params.get("to") ?? "");
  const [stops, setStops] = useState<string[]>([]);
  const [optimise, setOptimise] = useState(false);
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
        optimise,
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

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 print:hidden">
        <label className="grid gap-1 text-sm font-medium">
          From
          <Input value={origin} onChange={(e) => setOrigin(e.target.value)} required minLength={2} maxLength={200} className="h-11" placeholder="Town, place or address" />
        </label>
        {operator
          ? stops.map((stop, i) => (
              <div key={i} className="flex items-end gap-2">
                <label className="grid flex-1 gap-1 text-sm font-medium">
                  Stop {i + 1}
                  <Input value={stop} maxLength={200} className="h-11" onChange={(e) => setStops(stops.map((s, j) => (j === i ? e.target.value : s)))} />
                </label>
                <Button type="button" variant="outline" size="icon-lg" aria-label={`Remove stop ${i + 1}`} onClick={() => setStops(stops.filter((_, j) => j !== i))}>
                  <Trash2 />
                </Button>
              </div>
            ))
          : null}
        {operator && stops.length < MAX_STOPS ? (
          <Button type="button" variant="outline" size="lg" onClick={() => setStops([...stops, ""])}>
            <Plus /> Add stop ({stops.length}/{MAX_STOPS})
          </Button>
        ) : null}
        <label className="grid gap-1 text-sm font-medium">
          To
          <Input value={destination} onChange={(e) => setDestination(e.target.value)} required minLength={2} maxLength={200} className="h-11" placeholder="Town, place or address" />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Travel mode
          <select className={SELECT} disabled defaultValue="drive" aria-describedby="mode-note">
            <option value="drive">Driving (car or light vehicle)</option>
          </select>
          <span id="mode-note" className="text-xs font-normal text-slate-500">
            Truck height, weight and clearance rules are not checked.
          </span>
        </label>
        {operator ? (
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={optimise} onChange={(e) => setOptimise(e.target.checked)} />
            Optimise stop order (not available yet: stops stay in your order)
          </label>
        ) : null}
        <Button type="submit" size="lg" disabled={busy}>{busy ? "Planning…" : "Plan route"}</Button>
      </form>

      {error ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}

      {result ? (
        <div ref={resultRef} tabIndex={-1} className="space-y-5 outline-none" aria-live="polite">
          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="text-lg font-semibold">Route summary</h2>
            <p className="mt-1 text-slate-800">
              {result.places.map((p) => p.label).join(" → ")}
            </p>
            <p className="mt-1 text-sm">
              <strong>{formatKm(result.distance_m)}</strong>, about <strong>{formatDuration(result.duration_s)}</strong>
              <span className="text-slate-600"> · {result.duration_note}</span>
            </p>
            {result.provider === "mock" ? (
              <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900">Demonstration route: a straight line, not a road route.</p>
            ) : null}
            <p className="mt-1 text-xs text-slate-500">
              Alerts are matched within {Math.round(result.hazard_buffer_m)} m of the route.{" "}
              {result.data_updated_at ? `Alerts last updated ${formatWhen(result.data_updated_at)}.` : "No alerts have been published yet."}
            </p>
          </section>

          <PublicMapLazy label="Map of your route" className="h-80 overflow-hidden rounded-xl print:hidden" route={result.geometry as { type: string; coordinates: unknown }} markers={markers} />

          <section aria-labelledby="hz">
            <h2 id="hz" className="mb-2 text-lg font-semibold">Published alerts near this route</h2>
            {result.hazards.length ? (
              <ul className="space-y-2">{result.hazards.map((h) => <HazardItem key={h.alert_id} hazard={h} />)}</ul>
            ) : (
              <p className="text-sm text-slate-700">None found. This does not mean the road is safe.</p>
            )}
          </section>
          {result.closures.length ? (
            <section aria-labelledby="cl">
              <h2 id="cl" className="mb-2 text-lg font-semibold">Published road closures</h2>
              <ul className="space-y-2">{result.closures.map((h) => <HazardItem key={h.alert_id} hazard={h} />)}</ul>
              <p className="mt-1 text-xs text-slate-500">The route is not changed automatically to avoid closures.</p>
            </section>
          ) : null}
          <section aria-labelledby="bs">
            <h2 id="bs" className="mb-2 text-lg font-semibold">Historical blackspots (past risk, not current alerts)</h2>
            {result.blackspots.length ? (
              <ul className="space-y-2">
                {result.blackspots.map((b) => (
                  <li key={b.id} className="rounded-lg border border-violet-200 bg-white p-3 text-sm">
                    <p className="font-medium">{b.name}</p>
                    <p className="text-slate-600">About {Math.round(b.distance_from_route_m)} m from the route · Source: {b.source_name}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-700">No recorded blackspots near this route in our sourced data.</p>
            )}
          </section>
          {result.warnings.length ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
              {result.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          ) : null}
          <p role="note" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{result.disclaimer}</p>

          {operator ? (
            <div className="flex flex-wrap gap-3 print:hidden">
              <Button size="lg" onClick={() => window.print()}><Printer /> Print safety briefing</Button>
              <Button size="lg" variant="outline" onClick={copy}><Copy /> {copied ? "Copied" : "Copy summary"}</Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
