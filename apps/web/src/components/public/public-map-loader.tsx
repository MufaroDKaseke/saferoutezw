"use client";

import dynamic from "next/dynamic";
import { useI18n } from "@/lib/i18n/provider";
import type { PublicMapProps } from "./public-map";

function MapLoading() {
  const { t } = useI18n();
  return (
    <div className="flex min-h-72 items-center justify-center rounded-xl bg-slate-100 text-sm text-slate-500">
      {t("map.loadingMap")}
    </div>
  );
}

/** Leaflet and tiles load only when a map is actually shown (keeps first load light). */
export const PublicMapLazy = dynamic<PublicMapProps>(() => import("./public-map"), {
  ssr: false,
  loading: () => <MapLoading />,
});
