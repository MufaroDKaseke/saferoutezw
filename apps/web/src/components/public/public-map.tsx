"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { CircleMarker, GeoJSON, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { MAP_TILE_ATTRIBUTION, MAP_TILE_URL } from "@/lib/api/config";

export interface PublicMapMarker {
  id: string;
  lat: number;
  lng: number;
  title: string;
  subtitle?: string;
  href?: string;
  kind: "alert" | "blackspot" | "stop";
  approximate?: boolean;
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

const STYLE: Record<PublicMapMarker["kind"], { color: string; fill: string }> = {
  alert: { color: "#b91c1c", fill: "#ef4444" },
  blackspot: { color: "#6d28d9", fill: "#8b5cf6" },
  stop: { color: "#047857", fill: "#10b981" },
};

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

export default function PublicMap({ markers, route, label, className }: PublicMapProps) {
  return (
    <div className={className} role="region" aria-label={label}>
      <MapContainer
        bounds={ZIMBABWE_BOUNDS}
        minZoom={5}
        maxBounds={[
          [-26, 20],
          [-11, 38],
        ]}
        scrollWheelZoom={false}
        className="size-full min-h-72"
        style={{ background: "#e2e8f0" }}
      >
        <TileLayer url={MAP_TILE_URL} attribution={MAP_TILE_ATTRIBUTION} maxZoom={18} />
        <Fit route={route} markers={markers} />
        {route ? (
          <GeoJSON
            key={JSON.stringify(route).length}
            data={route as never}
            style={{ color: "#0f172a", weight: 4, opacity: 0.85 }}
          />
        ) : null}
        {markers.map((m) => {
          const style = STYLE[m.kind];
          return (
            <CircleMarker
              key={`${m.kind}-${m.id}`}
              center={[m.lat, m.lng]}
              radius={m.kind === "stop" ? 6 : 9}
              pathOptions={{
                color: style.color,
                fillColor: style.fill,
                fillOpacity: m.approximate ? 0.35 : 0.8,
                weight: 2,
                dashArray: m.kind === "blackspot" || m.approximate ? "4 4" : undefined,
              }}
            >
              <Tooltip>{m.title}</Tooltip>
              <Popup>
                <div className="space-y-1 text-[13px]">
                  <p className="font-semibold">{m.title}</p>
                  {m.subtitle ? <p className="text-slate-600">{m.subtitle}</p> : null}
                  {m.approximate ? <p className="text-slate-500">Approximate location</p> : null}
                  {m.href ? (
                    <a className="font-medium text-emerald-700 underline" href={m.href}>
                      Read the alert
                    </a>
                  ) : null}
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
