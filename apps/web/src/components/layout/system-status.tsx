"use client";

import { Chip } from "@/components/shared/status";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { getHealth } from "@/lib/api/health";
import { DEMO_NOW_ISO } from "@/lib/mock/clock";
import { formatTime } from "@/lib/formatters/date";
import { AlertTriangle, Check, FlaskConical } from "lucide-react";

/**
 * What kind of data is on screen, stated plainly. In mock mode there is no
 * "live" dot, because nothing is live. In api mode the badge reflects one real
 * GET /health check made when the page loaded (it is not polled).
 */
export function SystemStatus() {
  if (getDataMode() === "mock") {
    return (
      <div className="flex items-center gap-2">
        <Chip tone="amber" icon={FlaskConical} className="font-semibold">
          Demo data · not published
        </Chip>
        <span className="tnum hidden text-xs text-slate-600 2xl:inline">Snapshot {formatTime(DEMO_NOW_ISO)} CAT</span>
      </div>
    );
  }
  return <ApiStatus />;
}

function ApiStatus() {
  const health = useResource("system:health", () => getHealth());
  if (health.error) {
    return (
      <Chip tone="red" icon={AlertTriangle}>
        API unreachable
      </Chip>
    );
  }
  if (!health.data) return <Chip tone="slate">Checking API…</Chip>;
  return (
    <Chip tone="emerald" icon={Check}>
      API reachable · v{health.data.version}
    </Chip>
  );
}
