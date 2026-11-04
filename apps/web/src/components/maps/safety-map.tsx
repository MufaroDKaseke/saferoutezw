"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { MAP_TILE_ATTRIBUTION, MAP_TILE_URL } from "@/lib/api/config";
import { ACCURACY_LABEL, INCIDENT_TYPE_LABEL, RISK_LABEL } from "@/lib/formatters/labels";
import { formatShort } from "@/lib/formatters/date";
import { cn } from "@/lib/utils";
import { ReviewStateBadge } from "@/components/shared/status";
import type { Blackspot, Incident } from "@/types";
import { ACCURACY_RADIUS_M, clusterPoints, markerKind, type MapLayers, type MarkerKind } from "./map-logic";

/** Zimbabwe, framed so all provinces are visible. `bounds` only applies when `center`/`zoom` are not set. */
const ZIMBABWE_BOUNDS: L.LatLngBoundsExpression = [
  [-22.6, 25.1],
  [-15.5, 33.2],
];

/* -------------------------------------------------------------------- icons */

const ICON_HTML: Record<MarkerKind, string> = {
  reported:
    '<span style="display:flex;width:100%;height:100%;border-radius:9999px;background:#fff;border:3px solid #f59e0b;align-items:center;justify-content:center;font:700 13px/1 Inter,system-ui,sans-serif;color:#b45309;box-shadow:0 1px 3px rgba(15,23,42,.35)">!</span>',
  reviewed:
    '<span style="display:flex;width:100%;height:100%;border-radius:9999px;background:#fff;border:3px solid #0f172a;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(15,23,42,.35)"><span style="width:8px;height:8px;border-radius:9999px;background:#0f172a"></span></span>',
  approved:
    '<span style="display:flex;width:100%;height:100%;border-radius:9999px;background:#059669;border:3px solid #fff;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(15,23,42,.45)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>',
};

const KIND_LABEL: Record<MarkerKind, string> = {
  reported: "Reported, unverified",
  reviewed: "Reviewed, changes requested",
  approved: "Approved alert",
};

function incidentIcon(kind: MarkerKind, selected: boolean) {
  const size = selected ? 34 : 28;
  return L.divIcon({
    className: "szw-marker",
    html: `<div style="width:${size}px;height:${size}px;${selected ? "filter:drop-shadow(0 0 0 #0f172a) drop-shadow(0 0 6px rgba(15,23,42,.55));" : ""}">${ICON_HTML[kind]}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function clusterIcon(count: number) {
  const size = count > 9 ? 40 : 34;
  return L.divIcon({
    className: "szw-marker",
    html: `<div style="display:flex;width:${size}px;height:${size}px;border-radius:9999px;background:#0f172a;border:3px solid #fff;align-items:center;justify-content:center;color:#fff;font:700 13px/1 Inter,system-ui,sans-serif;box-shadow:0 1px 4px rgba(15,23,42,.5)">${count}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/* ------------------------------------------------------------------ helpers */

/**
 * At national zoom a 3 km blackspot is under 3 pixels wide and vanishes. Draw it
 * at least `minPx` wide on screen; once zoomed in, the true radius takes over.
 */
function visibleRadiusM(radiusM: number, lat: number, zoom: number, minPx: number): number {
  const metresPerPixel = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
  return Math.max(radiusM, minPx * metresPerPixel);
}

/** Follows zoom changes so clusters can re-form. */
function ZoomTracker({ onZoom }: { onZoom: (zoom: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  useEffect(() => {
    onZoom(map.getZoom());
  }, [map, onZoom]);
  return null;
}

/** Pans to whatever the list or table selected. */
function FlyTo({ target }: { target: { lat: number; lng: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], Math.max(map.getZoom(), 8), { duration: 0.6 });
  }, [map, target]);
  return null;
}

/**
 * A new key for every time the map is shown, and `null` while it is hidden or unmounted.
 *
 * Next's cache components keep a page's React tree alive but hidden when you navigate away, then
 * run its effects again when you come back. Leaflet cannot adopt a container it already used, so
 * the second activation threw "Map container is being reused by another instance" and, a moment
 * later, "Cannot read properties of undefined (reading 'appendChild')". Dropping the map when
 * its effects are torn down and mounting a fresh one (new container element) when they run again
 * avoids both.
 */
let mapSequence = 0;
function useFreshMapKey(): number | null {
  const [key, setKey] = useState<number | null>(null);
  useEffect(() => {
    // Deliberate: the key must change when effects re-run, which only an effect can observe.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setKey(++mapSequence);
    return () => setKey(null);
  }, []);
  return key;
}

export interface SafetyMapProps {
  incidents: Incident[];
  alertIncidentIds?: readonly string[];
  blackspots?: Blackspot[];
  layers: MapLayers;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  selectedBlackspotId?: string | null;
  onSelectBlackspot?: (id: string | null) => void;
  /** Label for assistive tech and the visible caption. */
  label?: string;
  className?: string;
}

export default function SafetyMap({
  incidents,
  alertIncidentIds = [],
  blackspots = [],
  layers,
  selectedId,
  onSelect,
  selectedBlackspotId,
  onSelectBlackspot,
  label = "Map of reported road incidents and historical blackspots in Zimbabwe",
  className,
}: SafetyMapProps) {
  const [zoom, setZoom] = useState(6);
  const mapKey = useFreshMapKey();
  const alertSet = useMemo(() => new Set(alertIncidentIds), [alertIncidentIds]);

  const visible = useMemo(
    () =>
      incidents
        .filter((i) => i.point)
        .map((i) => ({ incident: i, kind: markerKind(i, alertSet), id: i.id, lat: i.point!.lat, lng: i.point!.lng }))
        .filter((m) => layers[m.kind]),
    [incidents, alertSet, layers],
  );

  const clusters = useMemo(
    () => (layers.clusters ? clusterPoints(visible, zoom) : visible.map((m) => ({ key: m.id, lat: m.lat, lng: m.lng, members: [m] }))),
    [visible, zoom, layers.clusters],
  );

  const selected = incidents.find((i) => i.id === selectedId);
  const selectedBlackspot = blackspots.find((b) => b.id === selectedBlackspotId);
  const flyTarget = selected?.point ?? selectedBlackspot?.point ?? null;

  return (
    <div className={cn("relative isolate overflow-hidden rounded-xl", className)} role="region" aria-label={label}>
      {mapKey === null ? (
        <div className="size-full min-h-72" style={{ background: "#e2e8f0" }} aria-hidden="true" />
      ) : (
      <MapContainer
        key={mapKey}
        minZoom={5}
        maxBounds={[
          [-26, 20],
          [-11, 38],
        ]}
        bounds={ZIMBABWE_BOUNDS}
        scrollWheelZoom
        zoomSnap={0.25}
        zoomDelta={0.5}
        boundsOptions={{ padding: [4, 4] }}
        className="size-full min-h-72"
        style={{ background: "#e2e8f0" }}
      >
        <TileLayer url={MAP_TILE_URL} attribution={MAP_TILE_ATTRIBUTION} maxZoom={18} />
        <ZoomTracker onZoom={setZoom} />
        <FlyTo target={flyTarget} />

        {layers.blackspots
          ? blackspots.map((b) => (
              <Circle
                key={b.id}
                center={[b.point.lat, b.point.lng]}
                radius={visibleRadiusM(b.radiusKm * 1000, b.point.lat, zoom, 16)}
                pathOptions={{
                  color: "#dc2626",
                  weight: b.id === selectedBlackspotId ? 3 : 2,
                  dashArray: "6 6",
                  fillColor: "#ef4444",
                  fillOpacity: b.id === selectedBlackspotId ? 0.28 : 0.12,
                }}
                eventHandlers={{ click: () => onSelectBlackspot?.(b.id) }}
              >
                <Tooltip sticky>
                  {b.code} · {b.name}
                </Tooltip>
                <Popup>
                  <div className="space-y-1 text-[13px]">
                    <p className="font-bold">
                      {b.code} · {b.name}
                    </p>
                    {b.roadName ? <p>{b.roadName}</p> : null}
                    <p>Historical risk: {RISK_LABEL[b.riskLevel]}</p>
                    <p className="text-xs text-slate-600">
                      {b.synthetic ? "Synthetic demo blackspot. Not an official record, and not evidence that an incident happened." : `Source: ${b.dataSourceName}. Historical context, not evidence that an incident happened.`}
                    </p>
                  </div>
                </Popup>
              </Circle>
            ))
          : null}

        {selected?.point ? (
          <Circle
            center={[selected.point.lat, selected.point.lng]}
            radius={visibleRadiusM(ACCURACY_RADIUS_M[selected.point.accuracy], selected.point.lat, zoom, 10)}
            pathOptions={{ color: "#475569", weight: 1.5, dashArray: "2 5", fillColor: "#94a3b8", fillOpacity: 0.12 }}
            interactive={false}
          />
        ) : null}

        {clusters.map((c) => {
          if (c.members.length > 1) {
            return (
              <ClusterMarker key={c.key} lat={c.lat} lng={c.lng} count={c.members.length} points={c.members.map((m) => [m.lat, m.lng] as [number, number])} />
            );
          }
          const { incident, kind } = c.members[0];
          return (
            <Marker
              key={incident.id}
              position={[c.lat, c.lng]}
              icon={incidentIcon(kind, incident.id === selectedId)}
              title={`${incident.referenceCode}: ${incident.title}. ${KIND_LABEL[kind]}`}
              alt={`${incident.referenceCode}, ${KIND_LABEL[kind]}`}
              eventHandlers={{ click: () => onSelect?.(incident.id) }}
              zIndexOffset={incident.id === selectedId ? 1000 : 0}
            >
              <Popup minWidth={240}>
                <IncidentPopup incident={incident} kind={kind} />
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
      )}
    </div>
  );
}

function ClusterMarker({ lat, lng, count, points }: { lat: number; lng: number; count: number; points: [number, number][] }) {
  const map = useMap();
  return (
    <Marker
      position={[lat, lng]}
      icon={clusterIcon(count)}
      title={`${count} nearby reports. Press to zoom in.`}
      alt={`Cluster of ${count} nearby reports`}
      eventHandlers={{ click: () => map.fitBounds(L.latLngBounds(points), { padding: [60, 60], maxZoom: 11 }) }}
    />
  );
}

function IncidentPopup({ incident, kind }: { incident: Incident; kind: MarkerKind }) {
  return (
    <div className="space-y-2 text-[13px]">
      <div className="flex items-center justify-between gap-3">
        <span className="tnum text-xs text-slate-600">
          {incident.referenceCode} · {formatShort(incident.occurredAt ?? incident.createdAt)}
        </span>
        <ReviewStateBadge state={incident.reviewState} />
      </div>
      <p className="text-sm font-bold">{incident.title}</p>
      <p className="text-slate-700">{incident.locationText ?? "Location not stated"}</p>
      <p className="text-xs text-slate-600">
        {INCIDENT_TYPE_LABEL[incident.incidentType]} · {KIND_LABEL[kind]}
        {incident.point ? ` · ${ACCURACY_LABEL[incident.point.accuracy]} (illustrative position)` : ""}
      </p>
      <Link
        href={kind === "approved" ? `/incidents/${incident.id}` : `/reviews/${incident.id}`}
        className="inline-block font-semibold text-emerald-800 hover:underline"
      >
        {kind === "approved" ? "Open incident" : "Open in review workspace"}
      </Link>
    </div>
  );
}
