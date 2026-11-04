"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Check, Inbox, List, Map as MapIcon, Signal, SlidersHorizontal, Target } from "lucide-react";
import { HazardTag, HazardTile, SeverityBadge } from "@/components/public/hazard";
import { PublicMapLazy } from "@/components/public/public-map-loader";
import type { PublicMapMarker } from "@/components/public/public-map";
import { EmptyState, ErrorNotice } from "@/components/public/site-chrome";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/provider";
import {
  HAZARD_LABELS,
  describeError,
  formatWhen,
  publicApi,
  type PublicBlackspotList,
  type PublicMapCollection,
} from "@/lib/public-api/client";
import { markerHtml } from "@/lib/public-api/hazard-style";
import { cn } from "@/lib/utils";

const SELECT =
  "h-11 w-full rounded-xl border border-input bg-white px-3 text-sm text-slate-900 outline-none focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

type View = "map" | "list";

function Toggle({ pressed, onClick, children, tone = "slate" }: { pressed: boolean; onClick: () => void; children: React.ReactNode; tone?: "slate" | "indigo" }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-sm font-semibold transition-colors",
        pressed
          ? tone === "indigo"
            ? "border-indigo-700 bg-indigo-700 text-white"
            : "border-slate-900 bg-slate-900 text-white"
          : "border-slate-300 bg-white text-slate-800 hover:bg-slate-100",
      )}
    >
      {pressed ? <Check className="size-4" aria-hidden /> : null}
      {children}
    </button>
  );
}

function LegendMarker({ kind, hazard, severity }: { kind: PublicMapMarker["kind"]; hazard: string; severity: string }) {
  return <span aria-hidden className="inline-block size-7 shrink-0 [&>svg]:size-full" dangerouslySetInnerHTML={{ __html: markerHtml(kind, hazard, severity) }} />;
}

/** Collapsible so it never covers the map on a phone. Shape = type, fill = severity. */
function Legend() {
  const { t } = useI18n();
  const rows: Array<{ kind: PublicMapMarker["kind"]; hazard: string; severity: string; label: string }> = [
    { kind: "alert", hazard: "collision", severity: "fatal", label: t("map.legend.fatal") },
    { kind: "alert", hazard: "collision", severity: "serious", label: t("map.legend.serious") },
    { kind: "alert", hazard: "road_hazard", severity: "minor", label: t("map.legend.minor") },
    { kind: "alert", hazard: "road_closure", severity: "serious", label: t("map.legend.closure") },
    { kind: "alert", hazard: "traffic_disruption", severity: "minor", label: t("map.legend.disruption") },
    { kind: "blackspot", hazard: "blackspot", severity: "unknown", label: t("map.legend.blackspot") },
  ];
  return (
    <details className="group absolute bottom-3 left-3 z-[1000] max-w-[16.5rem] rounded-xl bg-white shadow-lg ring-1 ring-slate-900/10">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 text-sm font-semibold text-slate-900 select-none [&::-webkit-details-marker]:hidden">
        <Target className="size-4" aria-hidden /> {t("map.legend")}
      </summary>
      <ul className="space-y-1 px-3 pb-3">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2 text-[13px] text-slate-800">
            <LegendMarker kind={r.kind} hazard={r.hazard} severity={r.severity} />
            {r.label}
          </li>
        ))}
        <li className="pt-1 text-xs text-slate-600">{t("map.legend.approximate")}</li>
      </ul>
    </details>
  );
}

export function MapView() {
  const { t, rich, maybe, locale } = useI18n();
  const [hazard, setHazard] = useState("");
  const [severity, setSeverity] = useState("");
  const [days, setDays] = useState("");
  const [showAlerts, setShowAlerts] = useState(true);
  const [showBlackspots, setShowBlackspots] = useState(false);
  const [view, setView] = useState<View>("map");
  const filterKey = `${hazard}|${severity}|${days}`;
  // The outcome is stored with the filters it answers, so "loading" is derived (no setState in an effect).
  const [outcome, setOutcome] = useState<{ key: string; data: PublicMapCollection | null; error: unknown } | null>(null);
  const [blackspots, setBlackspots] = useState<PublicBlackspotList | null>(null);
  const [blackspotError, setBlackspotError] = useState<unknown>(null);
  const current = outcome?.key === filterKey ? outcome : null;
  const data = current?.data ?? null;
  const loading = current === null;
  const error = current?.error ?? blackspotError;
  const errorText = error ? describeError(error, t) : null;
  const activeFilters = [hazard, severity, days].filter(Boolean).length;

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
        setOutcome({ key: filterKey, data: null, error: e ?? new Error() });
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
        if (!controller.signal.aborted) setBlackspotError(e ?? new Error());
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
          subtitle: `${maybe(`hazard.${f.properties.hazard_type}`) ?? f.properties.hazard_type} · ${formatWhen(f.properties.published_at, locale)}`,
          href: f.properties.alert_url,
          kind: "alert",
          approximate: f.properties.location_precision !== "exact",
          severity: f.properties.severity,
          hazardType: f.properties.hazard_type,
        });
      }
    }
    if (showBlackspots && blackspots) {
      for (const b of blackspots.items) {
        out.push({
          id: b.id,
          lat: b.latitude,
          lng: b.longitude,
          title: t("blackspot.titled", { name: b.name }),
          subtitle: t("blackspot.sourced", { name: b.source_name }),
          kind: "blackspot",
        });
      }
    }
    return out;
  }, [data, blackspots, showAlerts, showBlackspots, maybe, locale, t]);

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-xs sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label={t("map.layers")} className="flex flex-wrap gap-2">
            <Toggle pressed={showAlerts} onClick={() => setShowAlerts(!showAlerts)}>
              {t("map.layerAlerts")}
            </Toggle>
            <Toggle pressed={showBlackspots} onClick={() => setShowBlackspots(!showBlackspots)} tone="indigo">
              {t("map.layerBlackspots")}
            </Toggle>
          </div>
          <div role="group" aria-label={t("map.view")} className="ml-auto inline-flex rounded-xl bg-slate-100 p-1">
            {(
              [
                ["map", t("map.viewMap"), MapIcon],
                ["list", t("map.viewList"), List],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                aria-pressed={view === value}
                onClick={() => setView(value)}
                className={cn(
                  "inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold sm:px-4",
                  view === value ? "bg-white text-slate-900 shadow-sm" : "text-slate-700 hover:text-slate-900",
                )}
              >
                <Icon className="size-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
        </div>

        <details className="group" open={activeFilters > 0}>
          <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 rounded-lg px-1 text-sm font-semibold text-slate-800 select-none [&::-webkit-details-marker]:hidden">
            <SlidersHorizontal className="size-4" aria-hidden /> {activeFilters ? t("alerts.filtersCount", { count: activeFilters }) : t("map.filters")}
          </summary>
          <form className="mt-2 grid gap-3 sm:grid-cols-3" onSubmit={(e) => e.preventDefault()}>
            <label className="grid gap-1 text-sm font-semibold">
              {t("alerts.hazardType")}
              <select className={SELECT} value={hazard} onChange={(e) => setHazard(e.target.value)}>
                <option value="">{t("alerts.allTypes")}</option>
                {Object.keys(HAZARD_LABELS).map((v) => (
                  <option key={v} value={v}>
                    {maybe(`hazard.${v}`) ?? v}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-sm font-semibold">
              {t("map.severity")}
              <select className={SELECT} value={severity} onChange={(e) => setSeverity(e.target.value)}>
                <option value="">{t("map.any")}</option>
                <option value="minor">{t("severity.minor.label")}</option>
                <option value="serious">{t("severity.serious.label")}</option>
                <option value="fatal">{t("severity.fatal.label")}</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm font-semibold">
              {t("map.published")}
              <select className={SELECT} value={days} onChange={(e) => setDays(e.target.value)}>
                <option value="">{t("map.anyTime")}</option>
                <option value="1">{t("map.last24h")}</option>
                <option value="7">{t("map.last7d")}</option>
                <option value="30">{t("map.last30d")}</option>
              </select>
            </label>
          </form>
        </details>
      </div>

      {errorText ? <ErrorNotice title={t("map.loadError")} message={errorText} /> : null}

      {data && data.unlocated_count > 0 ? (
        <p className="text-sm text-slate-600">
          {rich(
            "map.unlocated",
            {
              link: (c) => (
                <Link className="font-semibold text-emerald-800 underline" href="/public/alerts">
                  {c}
                </Link>
              ),
            },
            { count: data.unlocated_count },
          )}
        </p>
      ) : null}

      {view === "map" ? (
        <div className="space-y-2">
          <div className="relative">
            <PublicMapLazy label={t("map.label")} className="h-[65vh] min-h-[26rem] overflow-hidden rounded-2xl ring-1 ring-slate-200" markers={markers} />
            {loading ? (
              <p role="status" className="absolute top-3 left-1/2 z-[1000] -translate-x-1/2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-lg ring-1 ring-slate-900/10">
                {t("map.loading")}
              </p>
            ) : null}
            <Legend />
          </div>
          <p className="flex items-center gap-1.5 text-xs text-slate-600">
            <Signal className="size-3.5" aria-hidden /> {t("map.tilesNote")}
          </p>
        </div>
      ) : (
        <ul className="space-y-3" aria-label={t("map.listLabel")}>
          {markers.length === 0 && !loading ? (
            <li>
              <EmptyState icon={Inbox} title={t("map.listEmpty")}>
                {t("map.listEmptyBody")}
              </EmptyState>
            </li>
          ) : null}
          {loading ? (
            <li>
              <Skeleton className="h-24 rounded-2xl" role="status" aria-label={t("map.listLoading")} />
            </li>
          ) : null}
          {markers.map((m) => (
            <li key={`${m.kind}-${m.id}`} className="flex gap-3 rounded-2xl border border-slate-200 bg-white p-4">
              <HazardTile hazardType={m.hazardType ?? "other"} severity={m.severity} blackspot={m.kind === "blackspot"} />
              <div className="min-w-0 space-y-1.5 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  {m.kind === "alert" && m.severity && m.severity !== "unknown" ? <SeverityBadge severity={m.severity} /> : null}
                  {m.kind === "alert" ? <HazardTag hazardType={m.hazardType ?? "other"} /> : <span className="inline-flex h-7 items-center rounded-lg bg-indigo-100 px-2.5 text-[12.5px] font-semibold text-indigo-900">{t("blackspot.label")}</span>}
                </div>
                <p className="text-[15px] font-bold text-slate-900">
                  {m.href ? (
                    <Link className="underline-offset-2 hover:underline" href={m.href}>
                      {m.title}
                    </Link>
                  ) : (
                    m.title
                  )}
                </p>
                {m.subtitle ? <p className="text-slate-600">{m.subtitle}</p> : null}
                {m.approximate ? <p className="text-slate-500">{t("common.approximateLocation")}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {data?.last_updated ? <p className="text-xs text-slate-500">{t("map.latest", { when: formatWhen(data.last_updated, locale) })}</p> : null}
    </div>
  );
}
