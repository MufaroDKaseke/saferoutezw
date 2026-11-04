"use client";

import { PublicMapLazy } from "@/components/public/public-map-loader";

export function AlertMap({
  lat,
  lng,
  title,
  approximate,
}: {
  lat: number;
  lng: number;
  title: string;
  approximate: boolean;
}) {
  return (
    <PublicMapLazy
      label={`Map showing the location of: ${title}`}
      className="h-72 overflow-hidden rounded-xl"
      markers={[{ id: "alert", lat, lng, title, kind: "alert", approximate }]}
    />
  );
}
