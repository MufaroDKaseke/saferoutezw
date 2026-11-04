"use client";

import { PublicMapLazy } from "@/components/public/public-map-loader";
import { useI18n } from "@/lib/i18n/provider";

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
  const { t } = useI18n();
  return (
    <PublicMapLazy
      label={t("alert.mapLabel", { title })}
      className="h-72 overflow-hidden rounded-xl"
      markers={[{ id: "alert", lat, lng, title, kind: "alert", approximate }]}
    />
  );
}
