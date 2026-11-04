import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ArrowLeft, Clock, ExternalLink, MapPin, Route as RouteIcon } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { AlertMap } from "@/components/public/alert-map";
import { CopyLinkButton } from "@/components/public/copy-link-button";
import { HazardTag, HazardTile, SeverityBadge } from "@/components/public/hazard";
import { Container, ErrorNotice, Notice } from "@/components/public/site-chrome";
import { SubscribeCard } from "@/components/public/subscribe-cta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { attempt, formatWhen, publicApi, type PublicAlertDetail } from "@/lib/public-api/client";

export const metadata: Metadata = { title: "Road alert" };

async function Related({ alert }: { alert: PublicAlertDetail }) {
  if (!alert.province) return null;
  const { data } = await attempt(() => publicApi.alerts({ province: alert.province ?? undefined, page_size: 4 }));
  const items = (data?.items ?? []).filter((a) => a.id !== alert.id).slice(0, 2);
  if (!items.length) return null;
  return (
    <section aria-labelledby="related" className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <h2 id="related" className="text-2xl font-extrabold tracking-tight text-slate-900">
          More from {alert.province}
        </h2>
        <Link href={`/public/alerts?province=${encodeURIComponent(alert.province)}`} className="inline-flex min-h-11 items-center text-sm font-semibold text-emerald-800 underline underline-offset-2">
          All alerts in {alert.province}
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((a) => (
          <AlertCard key={a.id} alert={a} />
        ))}
      </div>
    </section>
  );
}

function Glance({ alert }: { alert: PublicAlertDetail }) {
  const rows: Array<[string, React.ReactNode]> = [
    ["Severity", <SeverityBadge key="s" severity={alert.severity} />],
    ["Hazard", <HazardTag key="h" hazardType={alert.hazard_type} />],
    ...(alert.road_name ? ([["Road", alert.road_name]] as Array<[string, React.ReactNode]>) : []),
    ...(alert.province ? ([["Province", alert.province]] as Array<[string, React.ReactNode]>) : []),
    ["Published", <time key="p" dateTime={alert.published_at}>{formatWhen(alert.published_at)}</time>],
    ["Last updated", <time key="u" dateTime={alert.updated_at}>{formatWhen(alert.updated_at)}</time>],
  ];
  return (
    <section aria-labelledby="glance" className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 id="glance" className="mb-1 font-bold text-slate-900">
        At a glance
      </h2>
      <dl className="divide-y divide-slate-100">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-2.5 text-sm">
            <dt className="text-slate-600">{label}</dt>
            <dd className="text-right font-semibold text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data: alert, error } = await attempt(() => publicApi.alert(id));
  if (error?.status === 404) notFound();
  if (error) return <ErrorNotice message={error.message} />;
  return (
    <div className="space-y-12">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
        <article className="space-y-6">
          <header className="space-y-4">
            <div className="flex items-center gap-3">
              <HazardTile hazardType={alert.hazard_type} severity={alert.severity} className="size-14 rounded-2xl" />
              <div className="flex flex-wrap items-center gap-2">
                {alert.severity !== "unknown" ? <SeverityBadge severity={alert.severity} /> : null}
                <HazardTag hazardType={alert.hazard_type} />
              </div>
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-balance text-slate-900 sm:text-4xl">{alert.headline}</h1>
            <dl className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-slate-700">
              {alert.location ? (
                <div className="flex items-center gap-1.5">
                  <MapPin className="size-4" aria-hidden />
                  <dt className="sr-only">Location</dt>
                  <dd>{alert.location}</dd>
                </div>
              ) : null}
              <div className="flex items-center gap-1.5">
                <Clock className="size-4" aria-hidden />
                <dt className="font-medium">Published</dt>
                <dd>
                  <time dateTime={alert.published_at}>{formatWhen(alert.published_at)}</time>
                </dd>
              </div>
              <div className="flex items-center gap-1.5">
                <dt className="font-medium">Last updated</dt>
                <dd>
                  <time dateTime={alert.updated_at}>{formatWhen(alert.updated_at)}</time>
                </dd>
              </div>
            </dl>
          </header>

          <Notice tone="warning" role="note">
            <strong className="font-semibold">Road conditions may have changed since this notice was published.</strong> {alert.notice}
          </Notice>

          <section aria-labelledby="bulletin" className="space-y-3">
            <h2 id="bulletin" className="text-xl font-extrabold tracking-tight text-slate-900">
              What happened
            </h2>
            <div className="max-w-prose text-[17px] leading-relaxed whitespace-pre-line text-slate-800">{alert.body}</div>
          </section>

          {alert.point ? (
            <section aria-labelledby="where" className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="where" className="text-xl font-extrabold tracking-tight text-slate-900">
                  Location
                </h2>
                <Link href="/public/map" className="inline-flex min-h-11 items-center text-sm font-semibold text-emerald-800 underline underline-offset-2">
                  Open the Safety Map
                </Link>
              </div>
              <AlertMap lat={alert.point.latitude} lng={alert.point.longitude} title={alert.headline} approximate={alert.point.precision !== "exact"} />
              <p className="text-sm text-slate-600">
                {alert.point.precision === "exact" ? "Position confirmed by an editor." : "Approximate position only; the exact spot may differ."}
              </p>
            </section>
          ) : (
            <p className="text-sm text-slate-600">No reliable map position is available for this notice.</p>
          )}

          {alert.sources.length ? (
            <section aria-labelledby="sources" className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5">
              <h2 id="sources" className="font-bold text-slate-900">
                Public sources
              </h2>
              <ul className="divide-y divide-slate-100">
                {alert.sources.map((s) => (
                  <li key={s.name} className="py-2 text-sm">
                    {s.url ? (
                      <a className="inline-flex min-h-9 items-center gap-1.5 font-semibold text-emerald-800 underline underline-offset-2" href={s.url} rel="noopener noreferrer" target="_blank">
                        {s.name} <ExternalLink className="size-3.5" aria-hidden />
                      </a>
                    ) : (
                      <span className="font-medium text-slate-800">{s.name}</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </article>

        <aside className="space-y-4" aria-label="Notice tools">
          <Glance alert={alert} />
          <section aria-labelledby="share" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
            <h2 id="share" className="font-bold text-slate-900">
              Share this notice
            </h2>
            <CopyLinkButton />
          </section>
          <SubscribeCard />
          <Button asChild variant="outline" size="lg" className="w-full">
            <Link href={alert.location ? `/public/routes?to=${encodeURIComponent(alert.location)}` : "/public/routes"}>
              <RouteIcon /> Plan a route
            </Link>
          </Button>
        </aside>
      </div>
      <Suspense fallback={null}>
        <Related alert={alert} />
      </Suspense>
    </div>
  );
}

export default function AlertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Container className="space-y-5 py-8 sm:py-10">
      <Link href="/public/alerts" className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-emerald-800 underline underline-offset-2">
        <ArrowLeft className="size-4" aria-hidden /> Back to alerts
      </Link>
      <Suspense fallback={<Skeleton className="h-96 rounded-2xl" role="status" aria-label="Loading alert" />}>
        <Detail params={params} />
      </Suspense>
    </Container>
  );
}
