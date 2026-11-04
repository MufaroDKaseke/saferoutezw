import Link from "next/link";
import { ChevronRight, Clock, MapPin } from "lucide-react";
import { HazardTag, HazardTile, SeverityBadge } from "@/components/public/hazard";
import { formatWhen, type PublicAlertSummary } from "@/lib/public-api/client";

/**
 * One published notice. Hazard icon, severity (icon + word + colour), headline, summary, place and time.
 * The whole card is clickable through the headline link; the visible label says where it goes.
 */
export function AlertCard({ alert }: { alert: PublicAlertSummary }) {
  return (
    <article className="group relative flex gap-3.5 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition-shadow hover:border-slate-300 hover:shadow-md has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-emerald-600 sm:p-5">
      <HazardTile hazardType={alert.hazard_type} severity={alert.severity} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {alert.severity !== "unknown" ? <SeverityBadge severity={alert.severity} /> : null}
          <HazardTag hazardType={alert.hazard_type} />
        </div>
        <h3 className="text-[17px] leading-snug font-bold tracking-tight text-slate-900">
          <Link href={`/public/alerts/${alert.id}`} className="outline-none after:absolute after:inset-0 after:content-['']">
            {alert.headline}
          </Link>
        </h3>
        <p className="line-clamp-3 text-sm leading-relaxed text-slate-600">{alert.summary}</p>
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-slate-600">
          {alert.location ? (
            <div className="flex items-center gap-1.5">
              <MapPin className="size-3.5" aria-hidden />
              <dt className="sr-only">Location</dt>
              <dd>{alert.location}</dd>
            </div>
          ) : null}
          <div className="flex items-center gap-1.5">
            <Clock className="size-3.5" aria-hidden />
            <dt className="sr-only">Published</dt>
            <dd>
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
        <span aria-hidden className="inline-flex items-center gap-0.5 text-sm font-semibold text-emerald-800 group-hover:underline">
          View details <ChevronRight className="size-4" />
        </span>
      </div>
    </article>
  );
}
