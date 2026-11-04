"use client";

import dynamic from "next/dynamic";
import type { PublicMapProps } from "./public-map";

/** Leaflet and tiles load only when a map is actually shown (keeps first load light). */
export const PublicMapLazy = dynamic<PublicMapProps>(() => import("./public-map"), {
  ssr: false,
  loading: () => (
    <div className="flex min-h-72 items-center justify-center rounded-xl bg-slate-100 text-sm text-slate-500">
      Loading map…
    </div>
  ),
});
