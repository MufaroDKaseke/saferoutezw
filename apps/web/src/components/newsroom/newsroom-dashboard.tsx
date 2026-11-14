"use client";

import Link from "next/link";
import { CalendarClock, Hourglass, Newspaper, NotebookPen, Radio, Rss, Sparkles, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceHealthList } from "@/components/dashboard/lists";
import { KpiCard } from "@/components/shared/kpi-card";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, EmptyState, QueryError } from "@/components/shared/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useResource } from "@/hooks/use-resource";
import { listNewsroomArticles, getNewsroomSummary } from "@/lib/api/newsroom";
import { listSources } from "@/lib/api/sources";
import { formatShort } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import { NewsCategoryBadge } from "./badges";

const number = (n: number) => n.toLocaleString("en-ZW");

/** NUST FM landing page: how the collection and classification are going, and the latest articles. */
export function NewsroomDashboard() {
  const summary = useResource("newsroom:summary", () => getNewsroomSummary());
  const latest = useResource("newsroom:latest", () => listNewsroomArticles({ pageSize: 8 }));
  const sources = useResource("newsroom:dashboard-sources", () => listSources());

  const s = summary.data;
  const maxCategory = Math.max(1, ...(s?.by_category.map((c) => c.count) ?? [1]));
  const maxPublisher = Math.max(1, ...(s?.publishers.map((p) => p.articles) ?? [1]));

  return (
    <div className="space-y-6">
      <PageHeader
        title="NUST FM — News Monitor"
        description="Articles collected from Zimbabwean news feeds and classified by AI. Everything here is unverified machine reading until a journalist checks the original."
        actions={
          <Button asChild>
            <Link href="/news">Open the News Monitor</Link>
          </Button>
        }
      />

      {summary.error ? (
        <QueryError error={summary.error} onRetry={summary.refetch} what="the newsroom summary" />
      ) : (
        <section aria-label="Key numbers" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
          {s ? (
            <>
              <KpiCard title="Collected articles" value={number(s.total_articles)} icon={Newspaper} tone="navy" hint="All time" />
              <KpiCard title="Collected today" value={number(s.collected_today)} icon={CalendarClock} tone="slate" hint="Since midnight, Harare time" />
              <KpiCard title="Classified today" value={number(s.classified_today)} icon={Sparkles} tone="indigo" hint="By the AI today" />
              <KpiCard
                title="Pending classification"
                value={number(s.pending_classification)}
                icon={Hourglass}
                tone="amber"
                hint="Collected, not yet read by the AI"
              />
              <KpiCard
                title="Processing failures"
                value={number(s.failures)}
                icon={TriangleAlert}
                tone={s.failures > 0 ? "red" : "slate"}
                emphasis={s.failures > 0}
                href="/news"
                hint={s.failures > 0 ? "Open an article to try again" : "None"}
              />
              <KpiCard
                title="Healthy RSS feeds"
                value={`${s.feeds.healthy} / ${s.feeds.enabled}`}
                icon={Rss}
                tone={s.feeds.unhealthy > 0 ? "amber" : "emerald"}
                href="/sources"
                hint={s.feeds.unhealthy > 0 ? `${s.feeds.unhealthy} need attention` : "All polled recently"}
              />
            </>
          ) : (
            Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)
          )}
        </section>
      )}

      {s ? (
        <section aria-label="Story to air" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            title="Stories awaiting approval"
            value={number(s.workflow.stories_awaiting_approval)}
            icon={Hourglass}
            tone={s.workflow.stories_awaiting_approval > 0 ? "amber" : "slate"}
            href="/stories"
            hint={s.workflow.stories_awaiting_approval > 0 ? "Scripts waiting for the Executive Producer" : "Nothing waiting"}
          />
          <KpiCard
            title="Stories in progress"
            value={number(s.workflow.stories_in_progress)}
            icon={NotebookPen}
            tone="slate"
            href="/stories"
            hint="Taken, not yet on air"
          />
          <KpiCard
            title="Bulletins awaiting approval"
            value={number(s.workflow.bulletins_awaiting_approval)}
            icon={Radio}
            tone={s.workflow.bulletins_awaiting_approval > 0 ? "amber" : "slate"}
            href="/bulletins"
            hint={s.workflow.bulletins_awaiting_approval > 0 ? "Revisions submitted for approval" : "Nothing waiting"}
          />
          <KpiCard
            title="Next bulletin"
            value={<span className="text-2xl">{s.workflow.next_bulletin ? s.workflow.next_bulletin.name : "None scheduled"}</span>}
            icon={CalendarClock}
            tone={s.workflow.next_bulletin?.approved_revision_number != null ? "emerald" : s.workflow.next_bulletin ? "amber" : "slate"}
            href={s.workflow.next_bulletin ? `/bulletins/${s.workflow.next_bulletin.id}` : "/bulletins"}
            hint={
              s.workflow.next_bulletin
                ? `${formatShort(s.workflow.next_bulletin.scheduled_for)} · target ${formatClock(s.workflow.next_bulletin.target_seconds)} · ${
                    s.workflow.next_bulletin.approved_revision_number != null
                      ? `revision ${s.workflow.next_bulletin.approved_revision_number} approved`
                      : "not approved yet"
                  }`
                : "Create one in Bulletins"
            }
          />
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <SectionCard
          title="Latest articles"
          description="Newest first, with the AI summary."
          action={<Link href="/news" className="font-semibold text-emerald-800 hover:underline">See all</Link>}
        >
          {latest.error ? (
            <QueryError error={latest.error} onRetry={latest.refetch} what="articles" />
          ) : !latest.data ? (
            <CardBodySkeleton lines={6} />
          ) : latest.data.items.length === 0 ? (
            <EmptyState title="No articles yet" description="They appear after the RSS feeds have been collected." />
          ) : (
            <ul className="divide-y divide-slate-100">
              {latest.data.items.map((a) => (
                <li key={a.id} className="space-y-1 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <NewsCategoryBadge category={a.category} />
                    <span className="tnum text-xs text-slate-600">
                      {a.publisher} · {formatShort(a.collected_at)}
                    </span>
                  </div>
                  <Link href={`/news/${a.id}`} className="block text-sm font-semibold hover:underline">
                    {a.headline}
                  </Link>
                  {a.summary ? <p className="line-clamp-2 text-xs text-slate-600">{a.summary}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <div className="space-y-6">
          <SectionCard title="Categories" description="Classified articles by primary category.">
            {s ? (
              <ul className="space-y-2">
                {s.by_category.map((c) => (
                  <li key={c.key}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium">{c.label}</span>
                      <span className="tnum text-slate-600">{number(c.count)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-indigo-500" style={{ width: `${(c.count / maxCategory) * 100}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <CardBodySkeleton lines={6} />
            )}
          </SectionCard>

          <SectionCard title="Publishers" description="Articles collected per source.">
            {s ? (
              s.publishers.length === 0 ? (
                <p className="text-sm text-slate-600">No sources have produced articles yet.</p>
              ) : (
                <ul className="space-y-2">
                  {s.publishers.slice(0, 10).map((p) => (
                    <li key={p.id}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium">{p.name}</span>
                        <span className="tnum text-slate-600">
                          {number(p.articles)} · {number(p.classified)} classified
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-slate-700" style={{ width: `${(p.articles / maxPublisher) * 100}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              )
            ) : (
              <CardBodySkeleton lines={4} />
            )}
          </SectionCard>

          {s ? (
            <SectionCard title="AI use today" description="From the model's own usage reports.">
              <p className="tnum text-sm">
                {number(s.usage_today.input_tokens)} tokens read · {number(s.usage_today.output_tokens)} tokens written
                {s.usage_today.estimated_cost_usd !== null ? ` · about US$${s.usage_today.estimated_cost_usd.toFixed(2)}` : ""}
              </p>
              {s.usage_today.estimated_cost_usd === null ? (
                <p className="mt-1 text-xs text-slate-600">No cost estimate: model prices are not configured.</p>
              ) : null}
            </SectionCard>
          ) : null}
        </div>
      </div>

      <SectionCard
        title="Source health"
        description="Last successful poll and failed polls per feed."
        action={<Link href="/sources" className="font-semibold text-emerald-800 hover:underline">Data sources</Link>}
      >
        {sources.error ? (
          <QueryError error={sources.error} onRetry={sources.refetch} what="the sources" />
        ) : !sources.data ? (
          <CardBodySkeleton lines={4} />
        ) : (
          <SourceHealthList sources={sources.data.slice(0, 24)} />
        )}
      </SectionCard>
    </div>
  );
}
