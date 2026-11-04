"use client";

import Link from "next/link";
import { Activity, AlertTriangle, BellRing, ClipboardCheck, FileSearch, Newspaper } from "lucide-react";
import { Button } from "@/components/ui/button";
import { KpiCard, KpiCardSkeleton } from "@/components/shared/kpi-card";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { SegmentedControl } from "@/components/shared/segmented";
import { QueryError, CardBodySkeleton } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useResource } from "@/hooks/use-resource";
import { getDashboard } from "@/lib/api/dashboard";
import { getDataMode } from "@/lib/api/config";
import { formatDayLong, referenceNow } from "@/lib/formatters/date";
import { useState, useSyncExternalStore } from "react";
import type { DashboardRange } from "@/types";
import { ActivityChart } from "./activity-chart";
import { QueuePreview, RecentNewsList, SourceHealthList } from "./lists";
import { MapPreview } from "./map-preview";
import { PipelineStrip } from "./pipeline-strip";

const RANGES = [
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
] as const;

const RANGE_TEXT: Record<DashboardRange, string> = {
  "24h": "last 24 hours",
  "7d": "last 7 days",
  "30d": "last 30 days",
};

const subscribeNever = () => () => {};

/** Today's date, rendered on the client only so it is never frozen into the prerender. */
function TodayLabel() {
  const label = useSyncExternalStore(subscribeNever, () => formatDayLong(referenceNow().toISOString()), () => "");
  return <p className="min-h-5 text-sm font-semibold">{label}</p>;
}

export function DashboardView() {
  const [range, setRange] = useState<DashboardRange>("7d");
  const dash = useResource(`dashboard:${range}`, () => getDashboard(range));
  const d = dash.data;
  const rangeText = RANGE_TEXT[range];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Road Safety Intelligence Overview"
        description="Monitor incoming reports, emerging road incidents and editorial activity across Zimbabwe."
        actions={
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <TodayLabel />
            {getDataMode() === "mock" ? <Chip tone="amber">Synthetic demo data · nothing is published</Chip> : null}
          </div>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="sr-only">Summary</h2>
        <SegmentedControl label="Time range" value={range} onChange={setRange} options={RANGES} />
        {dash.isFetching && d ? <span className="text-xs text-slate-600" role="status">Updating…</span> : null}
      </div>

      {dash.error ? (
        <SectionCard title="Summary">
          <QueryError error={dash.error} onRetry={dash.refetch} />
        </SectionCard>
      ) : (
        <>
          <PipelineStrip pipeline={d?.pipeline} rangeLabel={rangeText} />

          <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {!d ? (
              Array.from({ length: 6 }, (_, i) => <KpiCardSkeleton key={i} />)
            ) : (
              <>
                <KpiCard
                  title="Articles ingested"
                  value={d.kpis.articlesIngested}
                  icon={Newspaper}
                  hint={<>From RSS sources · {rangeText}</>}
                  href="/news"
                />
                <KpiCard
                  title="Road-relevant articles"
                  value={d.kpis.roadRelevantArticles}
                  icon={FileSearch}
                  hint={
                    <>
                      <strong className="text-slate-900">
                        {d.kpis.articlesIngested ? Math.round((d.kpis.roadRelevantArticles / d.kpis.articlesIngested) * 100) : 0}%
                      </strong>{" "}
                      matched the road-safety keywords. A match is not a verified accident.
                    </>
                  }
                  href="/news"
                />
                <KpiCard
                  title="Extracted incident candidates"
                  value={d.kpis.incidentCandidates}
                  icon={Activity}
                  tone="indigo"
                  hint={<>AI-extracted suggestions, not confirmed events</>}
                  href="/incidents"
                />
                <KpiCard
                  title="Pending editorial reviews"
                  value={d.kpis.pendingReviews}
                  icon={ClipboardCheck}
                  tone="amber"
                  hint={
                    <>
                      <strong className="text-amber-800">{d.kpis.highPriorityPending} high priority</strong>
                      {d.kpis.oldestPendingDays !== null ? ` · oldest ${d.kpis.oldestPendingDays} days` : ""}
                    </>
                  }
                  href="/reviews"
                />
                <KpiCard
                  title="Approved alerts"
                  value={d.kpis.approvedAlerts}
                  icon={BellRing}
                  tone="emerald"
                  hint={<>Approved is not the same as delivered</>}
                  href="/alerts"
                />
                <KpiCard
                  title="Failed processing jobs"
                  value={d.kpis.failedJobs}
                  icon={AlertTriangle}
                  tone={d.kpis.failedJobs > 0 ? "red" : "slate"}
                  emphasis={d.kpis.failedJobs > 0}
                  hint={
                    d.kpis.failedJobs > 0 ? (
                      <strong className="text-red-800">Articles waiting for a retry</strong>
                    ) : (
                      <>Nothing needs a retry</>
                    )
                  }
                  href="/processing"
                />
              </>
            )}
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <MapPreview />
            <SectionCard
              title="Recent news feed"
              description="Latest articles from RSS sources"
              action={
                <Link href="/news" className="font-semibold text-emerald-800 hover:underline">
                  View all
                </Link>
              }
            >
              {d ? <RecentNewsList items={d.recentNews} /> : <CardBodySkeleton lines={8} />}
            </SectionCard>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <SectionCard
              className="h-full"
              bodyClassName="flex flex-1 flex-col"
              title="Activity over time"
              description={`Articles and extracted incident candidates · ${rangeText}`}
            >
              {d ? <ActivityChart data={d.activity} range={range} /> : <CardBodySkeleton lines={6} />}
            </SectionCard>
            <SectionCard
              title="Editorial queue"
              description={d ? `${d.kpis.pendingReviews} awaiting a human decision, highest priority first` : undefined}
              action={
                <Button asChild variant="outline">
                  <Link href="/reviews">Open review queue</Link>
                </Button>
              }
            >
              {d ? <QueuePreview items={d.queue} /> : <CardBodySkeleton lines={6} />}
              <p className="mt-3 text-xs text-slate-600">
                AI confidence reflects how well fields were extracted from the article. It is not proof the event happened.
              </p>
            </SectionCard>
          </div>

          <SectionCard
            title="Source health"
            description="RSS sources, last successful poll and recent errors"
            action={
              <Link href="/sources" className="font-semibold text-emerald-800 hover:underline">
                Manage sources
              </Link>
            }
          >
            {d ? <SourceHealthList sources={d.sourceHealth} /> : <CardBodySkeleton lines={6} />}
          </SectionCard>
        </>
      )}
    </div>
  );
}
