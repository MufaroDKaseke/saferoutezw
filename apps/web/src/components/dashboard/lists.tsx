import Link from "next/link";
import { ConfidenceBar } from "@/components/shared/meter";
import { ConnectionBadge, RiskBadge, WorkflowBadge } from "@/components/shared/status";
import { EmptyState } from "@/components/shared/states";
import { formatRelative, formatShort } from "@/lib/formatters/date";
import { INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import { cn } from "@/lib/utils";
import type { ReviewQueueItem, SourceItem, SourceSummary } from "@/types";

/** Latest articles from the RSS pipeline. An article is a source report, not an incident. */
export function RecentNewsList({ items }: { items: SourceItem[] }) {
  if (items.length === 0) {
    return <EmptyState title="No incident candidates yet" description="Posts appear here once one has been turned into an incident candidate." />;
  }
  return (
    <ul className="-mx-2 divide-y divide-slate-100">
      {items.map((a) => (
        <li key={a.id}>
          <Link href={`/news/${a.id}`} className="block rounded-lg px-2 py-3 hover:bg-slate-50">
            <p className="text-sm leading-snug font-semibold text-foreground">{a.titleRedacted}</p>
            <p className="tnum mt-1 text-xs text-slate-600">
              {a.publisherName} · {formatRelative(a.receivedAt)}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <WorkflowBadge state={a.workflowState} />
              {a.screening ? (
                <span className="text-xs text-slate-600">
                  {a.screening.score === null ? (
                    a.screening.decision === "relevant" ? "Passed keyword screen" : "Filtered by keyword screen"
                  ) : (
                    <>
                      Keyword score <span className="tnum font-medium">{a.screening.score.toFixed(2)}</span>
                    </>
                  )}
                </span>
              ) : (
                <span className="text-xs text-slate-600">Not screened yet</span>
              )}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Incidents waiting for a human, highest priority first. */
export function QueuePreview({ items }: { items: ReviewQueueItem[] }) {
  if (items.length === 0) {
    return <EmptyState title="The queue is clear" description="Nothing is waiting for an editor." />;
  }
  return (
    <div className="-mx-(--card-spacing) overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <caption className="sr-only">Incident candidates awaiting editorial review</caption>
        <thead>
          <tr className="border-y bg-slate-50/70 text-left text-[11.5px] font-semibold tracking-[0.06em] text-slate-500 uppercase">
            <th scope="col" className="px-5 py-2.5">ID</th>
            <th scope="col" className="px-3 py-2.5">Incident</th>
            <th scope="col" className="px-3 py-2.5">AI confidence</th>
            <th scope="col" className="px-3 py-2.5">Area risk</th>
            <th scope="col" className="px-5 py-2.5"><span className="sr-only">Action</span></th>
          </tr>
        </thead>
        <tbody>
          {items.map((q) => (
            <tr key={q.incidentId} className="border-b border-slate-100 last:border-0">
              <td className="tnum px-5 py-3 font-mono text-xs whitespace-nowrap text-slate-700">{q.referenceCode}</td>
              <td className="px-3 py-3">
                <p className="font-semibold">{q.title}</p>
                <p className="text-xs text-slate-600">
                  {INCIDENT_TYPE_LABEL[q.incidentType]} · {q.locationText ?? "Location not stated"}
                </p>
              </td>
              <td className="px-3 py-3">
                <ConfidenceBar value={q.extractionConfidence} />
              </td>
              <td className="px-3 py-3">
                <RiskBadge level={q.riskLevel} />
              </td>
              <td className="px-5 py-3 text-right">
                <Link href={`/reviews/${q.incidentId}`} className="font-semibold text-emerald-800 hover:underline">
                  Review<span className="sr-only"> {q.referenceCode}</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Feed health at a glance: status, last successful poll, error count. */
export function SourceHealthList({ sources }: { sources: SourceSummary[] }) {
  return (
    <ul className="grid gap-x-10 lg:grid-cols-2">
      {sources.map((s) => (
        <li key={s.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-slate-100 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{s.name}</p>
            <p className={cn("tnum text-xs", s.connectionStatus === "failing" ? "text-red-800" : "text-slate-600")}>
              {s.lastSuccessfulPollAt
                ? `Last success ${formatShort(s.lastSuccessfulPollAt)}`
                : "No successful poll yet"}
              {s.errorCount > 0 ? ` · ${s.errorCount} failed ${s.errorCount === 1 ? "poll" : "polls"}` : ""}
            </p>
          </div>
          <ConnectionBadge status={s.connectionStatus} />
        </li>
      ))}
    </ul>
  );
}
