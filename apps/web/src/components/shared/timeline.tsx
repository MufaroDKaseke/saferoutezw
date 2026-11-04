import { Clock, Sparkles, User } from "lucide-react";
import { formatShort } from "@/lib/formatters/date";
import { STAGE_LABEL } from "@/lib/formatters/labels";
import { cn } from "@/lib/utils";
import type { AuditEvent, PipelineStage } from "@/types";
import { STAGE_STYLE, StageStatus } from "./status";

/**
 * Append-only activity log. Actor colour follows the concept: indigo for the AI,
 * slate for the system, navy for a named human. The actor is always named too.
 */
const ACTOR = {
  ai: { icon: Sparkles, className: "bg-indigo-100 text-indigo-700" },
  system: { icon: Clock, className: "bg-slate-200 text-slate-600" },
  human: { icon: User, className: "bg-slate-900 text-white" },
} as const;

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="relative space-y-4">
      {events.map((event, index) => {
        const actor = ACTOR[event.actorKind];
        const Icon = actor.icon;
        return (
          <li key={event.id} className="relative flex gap-3">
            {index < events.length - 1 ? (
              <span className="absolute top-8 left-[15px] h-[calc(100%-8px)] w-px bg-slate-200" aria-hidden />
            ) : null}
            <span className={cn("z-10 flex size-8 shrink-0 items-center justify-center rounded-full", actor.className)}>
              <Icon className="size-3.5" aria-hidden />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-sm leading-snug font-semibold text-foreground">{event.summary}</p>
              <p className="tnum mt-0.5 text-xs text-slate-600">
                {formatShort(event.occurredAt)} · {event.actorName} · entry #{event.entryRef}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** The eight pipeline stages in order. This is a genuine sequence, so it is numbered. */
export function PipelineTimeline({ stages }: { stages: PipelineStage[] }) {
  return (
    <ol className="space-y-3">
      {stages.map((stage, index) => {
        const style = STAGE_STYLE[stage.status];
        const Icon = style.icon;
        return (
          <li key={stage.id} className="flex gap-3">
            <span
              className={cn(
                "flex size-8 shrink-0 items-center justify-center rounded-full",
                stage.status === "completed" && "bg-emerald-100 text-emerald-800",
                stage.status === "failed" && "bg-red-100 text-red-800",
                stage.status === "pending" && "bg-amber-100 text-amber-800",
                stage.status === "skipped" && "bg-slate-100 text-slate-500",
              )}
            >
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-sm font-semibold text-foreground">
                  <span className="tnum mr-1.5 text-slate-500">{index + 1}.</span>
                  {STAGE_LABEL[stage.id]}
                </p>
                <StageStatus status={stage.status} />
                {stage.at ? <span className="tnum text-xs text-slate-600">{formatShort(stage.at)}</span> : null}
              </div>
              {stage.detail ? <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{stage.detail}</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
