import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ArrowLeft } from "lucide-react";
import { AlertMap } from "@/components/public/alert-map";
import { ErrorNotice } from "@/components/public/site-chrome";
import { Badge } from "@/components/ui/badge";
import { HAZARD_LABELS, attempt, formatWhen, publicApi } from "@/lib/public-api/client";

export const metadata: Metadata = { title: "Road alert" };

async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data: alert, error } = await attempt(() => publicApi.alert(id));
  if (error?.status === 404) notFound();
  if (error) return <ErrorNotice message={error.message} />;
  return (
    <article className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{HAZARD_LABELS[alert.hazard_type] ?? alert.hazard_type}</Badge>
        {alert.severity !== "unknown" ? <Badge variant="secondary" className="capitalize">{alert.severity}</Badge> : null}
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">{alert.headline}</h1>
      <dl className="grid gap-1 text-sm text-slate-700 sm:grid-cols-2">
        {alert.location ? (
          <div><dt className="inline font-medium">Location: </dt><dd className="inline">{alert.location}</dd></div>
        ) : null}
        <div>
          <dt className="inline font-medium">Published: </dt>
          <dd className="inline"><time dateTime={alert.published_at}>{formatWhen(alert.published_at)}</time></dd>
        </div>
        <div>
          <dt className="inline font-medium">Last updated: </dt>
          <dd className="inline"><time dateTime={alert.updated_at}>{formatWhen(alert.updated_at)}</time></dd>
        </div>
      </dl>
      <div className="whitespace-pre-line rounded-xl border border-slate-200 bg-white p-4 text-slate-800">{alert.body}</div>
      {alert.sources.length ? (
        <section aria-labelledby="sources">
          <h2 id="sources" className="mb-1 text-base font-semibold">Sources</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {alert.sources.map((s) => (
              <li key={s.name}>
                {s.url ? <a className="underline" href={s.url} rel="noopener noreferrer" target="_blank">{s.name}</a> : s.name}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {alert.point ? (
        <section aria-labelledby="where" className="space-y-2">
          <h2 id="where" className="text-base font-semibold">Where</h2>
          <p className="text-sm text-slate-600">
            {alert.point.precision === "exact" ? "Position confirmed by an editor." : "Approximate position only; the exact spot may differ."}
          </p>
          <AlertMap lat={alert.point.latitude} lng={alert.point.longitude} title={alert.headline} approximate={alert.point.precision !== "exact"} />
        </section>
      ) : (
        <p className="text-sm text-slate-600">No reliable map position is available for this notice.</p>
      )}
      <p role="note" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{alert.notice}</p>
    </article>
  );
}

export default function AlertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <div className="space-y-4">
      <Link href="/public/alerts" className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-emerald-800 underline">
        <ArrowLeft className="size-4" /> All alerts
      </Link>
      <Suspense fallback={<p className="text-sm text-slate-500">Loading alert…</p>}>
        <Detail params={params} />
      </Suspense>
    </div>
  );
}
