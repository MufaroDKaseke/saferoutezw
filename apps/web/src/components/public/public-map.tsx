"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { MAP_TILE_ATTRIBUTION, MAP_TILE_URL } from "@/lib/api/config";
import { useI18n } from "@/lib/i18n/provider";
import { markerHtml } from "@/lib/public-api/hazard-style";
import { MAP_MIN_ZOOM, REGION_BOUNDS, padBounds } from "@/lib/scope";

export interface PublicMapMarker {
  id: string;
  lat: number;
  lng: number;
  title: string;
  subtitle?: string;
  href?: string;
  kind: "alert" | "blackspot" | "stop";
  approximate?: boolean;
  /** Editor-approved severity: fatal, serious, minor or unknown. Drives the marker fill. */
  severity?: string;
  hazardType?: string;
}

export interface PublicMapProps {
  markers: PublicMapMarker[];
  /** GeoJSON LineString / MultiLineString from the routing engine. */
  route?: { type: string; coordinates: unknown } | null;
  label: string;
  className?: string;
}

const ZIMBABWE_BOUNDS: L.LatLngBoundsExpression = [
  [-22.5, 25.2],
  [-15.6, 33.1],
];

function Fit({ route, markers }: Pick<PublicMapProps, "route" | "markers">) {
  const map = useMap();
  useEffect(() => {
    if (route) {
      const bounds = L.geoJSON(route as never).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
    }
  }, [map, route, markers.length]);
  return null;
}

function iconFor(m: PublicMapMarker) {
  const size = m.kind === "stop" ? 28 : 40;
  return L.divIcon({
    html: markerHtml(m.kind, m.hazardType ?? "other", m.severity ?? "unknown", m.approximate),
    className: "saferoute-marker",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

export default function PublicMap({ markers, route, label, className }: PublicMapProps) {
  const { t } = useI18n();
  return (
    <div className={className} role="region" aria-label={label}>
      <MapContainer
        bounds={REGION_BOUNDS ?? ZIMBABWE_BOUNDS}
        minZoom={MAP_MIN_ZOOM}
        maxBounds={
          REGION_BOUNDS
            ? padBounds(REGION_BOUNDS, 0.5)
            : [
                [-26, 20],
                [-11, 38],
              ]
        }
        scrollWheelZoom={false}
        className="size-full min-h-72"
        style={{ background: "#e2e8f0" }}
      >
        <TileLayer url={MAP_TILE_URL} attribution={MAP_TILE_ATTRIBUTION} maxZoom={18} />
        <Fit route={route} markers={markers} />
        {route ? (
          <>
            <GeoJSON key={`c-${JSON.stringify(route).length}`} data={route as never} style={{ color: "#ffffff", weight: 9, opacity: 0.9 }} />
            <GeoJSON key={`r-${JSON.stringify(route).length}`} data={route as never} style={{ color: "#047857", weight: 5, opacity: 1 }} />
          </>
        ) : null}
        {markers.map((m) => (
          <Marker key={`${m.kind}-${m.id}`} position={[m.lat, m.lng]} icon={iconFor(m)} title={m.title} keyboard>
            <Tooltip>{m.title}</Tooltip>
            <Popup>
              <div className="space-y-1 text-[13px]">
                <p className="font-semibold">{m.title}</p>
                {m.subtitle ? <p className="text-slate-600">{m.subtitle}</p> : null}
                {m.approximate ? <p className="text-slate-500">{t("common.approximateLocation")}</p> : null}
                {m.href ? (
                  <a className="font-semibold text-emerald-700 underline" href={m.href}>
                    {t("map.readAlert")}
                  </a>
                ) : null}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
