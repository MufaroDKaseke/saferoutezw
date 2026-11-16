"use client";

import { Chip } from "@/components/shared/status";
import { getDataMode } from "@/lib/api/config";
import { DEMO_NOW_ISO } from "@/lib/mock/clock";
import { formatTime } from "@/lib/formatters/date";
import { FlaskConical } from "lucide-react";

/**
 * Keep the synthetic-data notice visible in demo mode.
 * Production headers do not show API status or make a health request.
 */
export function SystemStatus() {
  if (getDataMode() !== "mock") return null;
  return (
    <div className="hidden items-center gap-2 xl:flex">
      <Chip tone="amber" icon={FlaskConical} className="font-semibold">
        Demo data · not published
      </Chip>
      <span className="tnum hidden text-xs text-slate-600 2xl:inline">Snapshot {formatTime(DEMO_NOW_ISO)} CAT</span>
    </div>
  );
}
