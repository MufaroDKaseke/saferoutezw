"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { MapLegend } from "@/components/maps/map-controls";
import { DEFAULT_LAYERS } from "@/components/maps/map-logic";
import { SafetyMap } from "@/components/maps/safety-map-loader";
import { SectionCard } from "@/components/shared/section-card";
import { QueryError } from "@/components/shared/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { getMapData } from "@/lib/api/incidents";
import { SCOPE_NAME } from "@/lib/scope";

/**
 * Compact map for the dashboard. Only incidents that have coordinates are
 * plotted, and in demo mode the positions are labelled as illustrative.
 */
export function MapPreview() {
  const map = useResource("dashboard:map", () => getMapData({}));
  const [openOnly, setOpenOnly] = useState(false);

  const incidents = useMemo(
    () => (map.data?.incidents ?? []).filter((i) => !openOnly || i.reviewState === "pending" || i.reviewState === "needs_changes"),
    [map.data, openOnly],
  );

  return (
    <SectionCard
      className="h-full"
      bodyClassName="flex flex-1 flex-col"
      title={`${SCOPE_NAME} incident map`}
      description="Reported items are unverified until an editor approves them."
      action={
        <Button asChild variant="outline">
          <Link href="/map">Open safety map</Link>
        </Button>
      }
    >
      {map.error ? (
        <QueryError error={map.error} onRetry={map.refetch} />
      ) : !map.data ? (
        <Skeleton className="h-[380px] w-full rounded-xl" />
      ) : (
        <div className="flex flex-1 flex-col gap-3">
          <div className="flex items-center gap-2">
            <Checkbox id="open-only" checked={openOnly} onCheckedChange={(v) => setOpenOnly(v === true)} />
            <Label htmlFor="open-only" className="text-sm font-medium">
              Show only reports awaiting a decision
            </Label>
          </div>
          <div className="relative min-h-[380px] flex-1">
            <SafetyMap
              incidents={incidents}
              alertIncidentIds={map.data.alertIncidentIds}
              blackspots={map.data.blackspots}
              layers={DEFAULT_LAYERS}
              className="h-full"
            />
          </div>
          <MapLegend inline />
          <p className="text-xs text-slate-600">
            {getDataMode() === "mock"
              ? "Marker and blackspot positions are synthetic and illustrative only. They are not official coordinates."
              : "Only incidents with a recorded position are shown. Position accuracy appears in each marker’s details."}
          </p>
        </div>
      )}
    </SectionCard>
  );
}
