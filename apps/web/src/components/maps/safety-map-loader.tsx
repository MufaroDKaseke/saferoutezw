"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function MapSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-slate-100", className)} aria-busy="true">
      <span role="status" className="sr-only">
        Loading map…
      </span>
      <Skeleton className="size-full min-h-72 rounded-xl" />
    </div>
  );
}

/**
 * Leaflet touches `window`, so it only loads in the browser. The skeleton keeps
 * the layout stable while the map bundle arrives.
 */
export const SafetyMap = dynamic(() => import("./safety-map"), {
  ssr: false,
  loading: () => <MapSkeleton className="h-full" />,
});
