import { Check, Clock, Inbox, Send, Sparkles, type LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DashboardPipeline } from "@/types";

const STEPS: { key: keyof DashboardPipeline; label: string; icon: LucideIcon; tone: string }[] = [
  { key: "ingested", label: "Articles ingested", icon: Inbox, tone: "bg-slate-100 text-slate-600" },
  { key: "aiExtracted", label: "AI-extracted (suggestions only)", icon: Sparkles, tone: "bg-indigo-100 text-indigo-700" },
  { key: "awaitingDecision", label: "Awaiting human decision", icon: Clock, tone: "bg-amber-100 text-amber-700" },
  { key: "approvedByEditor", label: "Approved by an editor", icon: Check, tone: "bg-emerald-100 text-emerald-700" },
  { key: "fullyShared", label: "Fully shared with the public", icon: Send, tone: "bg-slate-900 text-white" },
];

/**
 * The concept's "how a report becomes an alert" strip. Each step is its own
 * count, so approval and distribution are never blended into one figure.
 */
export function PipelineStrip({ pipeline, rangeLabel }: { pipeline?: DashboardPipeline; rangeLabel: string }) {
  return (
    <Card aria-labelledby="pipeline-heading">
      <div className="px-(--card-spacing)">
        <h2 id="pipeline-heading" className="section-label">
          How an article becomes an alert · {rangeLabel}
        </h2>
      </div>
      <ol className="grid grid-cols-2 gap-x-4 gap-y-5 px-(--card-spacing) sm:grid-cols-3 lg:grid-cols-5">
        {STEPS.map(({ key, label, icon: Icon, tone }) => (
          <li key={key} className="flex items-start gap-3">
            <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-lg", tone)}>
              <Icon className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              {pipeline ? (
                <p className="tnum text-[26px] leading-none font-bold">{pipeline[key]}</p>
              ) : (
                <Skeleton className="h-6 w-8" />
              )}
              <p className="mt-1 text-xs leading-snug text-slate-600">{label}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
