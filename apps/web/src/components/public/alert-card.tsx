import Link from "next/link";
import { MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { HAZARD_LABELS, formatWhen, type PublicAlertSummary } from "@/lib/public-api/client";

export function AlertCard({ alert }: { alert: PublicAlertSummary }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{HAZARD_LABELS[alert.hazard_type] ?? alert.hazard_type}</Badge>
        {alert.severity !== "unknown" ? <Badge variant="secondary" className="capitalize">{alert.severity}</Badge> : null}
      </div>
      <h3 className="text-base font-semibold text-slate-900">
        <Link href={`/public/alerts/${alert.id}`} className="underline-offset-2 hover:underline">
          {alert.headline}
        </Link>
      </h3>
      <p className="mt-1 text-sm text-slate-700">{alert.summary}</p>
      <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {alert.location ? (
          <div className="flex items-center gap-1">
            <MapPin className="size-3.5" aria-hidden />
            <dt className="sr-only">Location</dt>
            <dd>{alert.location}</dd>
          </div>
        ) : null}
        <div>
          <dt className="inline">Published </dt>
          <dd className="inline">
            <time dateTime={alert.published_at}>{formatWhen(alert.published_at)}</time>
          </dd>
        </div>
        {alert.sources.length ? (
          <div>
            <dt className="inline">Source: </dt>
            <dd className="inline">{alert.sources.map((s) => s.name).join(", ")}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}
