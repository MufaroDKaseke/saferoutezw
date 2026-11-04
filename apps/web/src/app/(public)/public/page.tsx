import Link from "next/link";
import { Suspense } from "react";
import { ArrowRight, Bell, Clock, FileSearch, Inbox, ListChecks, Map as MapIcon, ShieldCheck, Truck } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { JourneyForm } from "@/components/public/journey-form";
import { RouteArt } from "@/components/public/route-art";
import { Container, EmptyState, ErrorNotice } from "@/components/public/site-chrome";
import { SubscribeBand } from "@/components/public/subscribe-cta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { attempt, formatWhen, publicApi } from "@/lib/public-api/client";

const QUICK_ACTIONS = [
  { href: "/public/alerts", label: "Road Alerts", text: "Published notices, newest first.", icon: ListChecks },
  { href: "/public/map", label: "Safety Map", text: "Hazards and blackspots on a map.", icon: MapIcon },
  { href: "/public/subscribe", label: "Get Alerts", text: "SMS or WhatsApp, free, no account.", icon: Bell },
  { href: "/public/operators", label: "Transport Operators", text: "Multi-stop planner and driver briefing.", icon: Truck },
];

const STEPS = [
  { icon: FileSearch, title: "Reports are gathered", text: "From news outlets and official sources." },
  { icon: ShieldCheck, title: "An editor reviews", text: "A person checks each report and decides whether to publish it." },
  { icon: Bell, title: "You are informed", text: "Published here, and sent by SMS or WhatsApp if you subscribe." },
];

function Hero() {
  return (
    <section className="relative overflow-hidden bg-slate-900 text-white">
      <Container className="grid items-center gap-8 py-10 sm:py-14 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:py-16">
        <div className="space-y-5">
          <p className="text-sm font-semibold text-emerald-300">Road safety for Zimbabwe</p>
          <h1 className="text-5xl font-extrabold tracking-tight text-balance sm:text-6xl">Know the road ahead.</h1>
          <p className="max-w-lg text-lg leading-relaxed text-slate-300">
            Check road safety updates, plan your journey and stay informed across Zimbabwe.
          </p>
          <JourneyForm />
          <p className="flex items-center gap-2 text-sm text-slate-300">
            <ShieldCheck className="size-4 shrink-0 text-emerald-400" aria-hidden />
            Every notice is reviewed by a human editor before it is published.
          </p>
        </div>
        <RouteArt className="h-44 overflow-hidden rounded-3xl ring-1 ring-white/10 sm:h-64 lg:h-[30rem]" />
      </Container>
    </section>
  );
}

function QuickActions() {
  return (
    <nav aria-label="Quick actions" className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
      {QUICK_ACTIONS.map(({ href, label, text, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className="group flex min-h-32 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs transition-shadow hover:border-slate-300 hover:shadow-md"
        >
          <span className="flex size-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
            <Icon className="size-6" />
          </span>
          <span className="space-y-0.5">
            <span className="block text-base font-bold text-slate-900 group-hover:underline">{label}</span>
            <span className="block text-[13px] leading-snug text-slate-600 sm:text-sm">{text}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}

function LatestSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-2" role="status" aria-label="Loading notices">
      {[0, 1].map((i) => (
        <Skeleton key={i} className="h-40 rounded-2xl" />
      ))}
    </div>
  );
}

async function LatestAlerts() {
  const { data: summary, error } = await attempt(() => publicApi.summary());
  if (error) return <ErrorNotice message={error.message} />;
  const count = summary.recent_alert_count;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-slate-200 bg-white px-5 py-4">
        <p className="text-sm text-slate-700">
          <strong className="mr-1 text-2xl font-extrabold tracking-tight text-slate-900 tnum">{count}</strong>
          published notice{count === 1 ? "" : "s"} in the last {summary.window_days} days
        </p>
        {summary.last_updated ? (
          <p className="flex items-center gap-1.5 text-sm text-slate-600">
            <Clock className="size-4" aria-hidden /> Last update {formatWhen(summary.last_updated)}
          </p>
        ) : null}
      </div>
      {summary.latest_alerts.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="There are no published notices right now"
          actions={
            <>
              <Button asChild variant="approve" size="lg">
                <Link href="/public/subscribe">
                  <Bell /> Tell me when one is published
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/public/map">Open the map</Link>
              </Button>
            </>
          }
        >
          This does not mean roads are free of hazards. Check again before you travel.
        </EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {summary.latest_alerts.slice(0, 4).map((a) => (
            <AlertCard key={a.id} alert={a} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PublicHome() {
  return (
    <>
      <Hero />
      <Container className="space-y-14 py-8 sm:space-y-16 sm:py-12">
        <QuickActions />

        <section aria-labelledby="latest" className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="latest" className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
              Latest road safety notices
            </h2>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">
                View all alerts <ArrowRight />
              </Link>
            </Button>
          </div>
          <Suspense fallback={<LatestSkeleton />}>
            <LatestAlerts />
          </Suspense>
        </section>

        <SubscribeBand />

        <section id="how" aria-labelledby="how-h" className="scroll-mt-24 space-y-5">
          <h2 id="how-h" className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            How a notice reaches you
          </h2>
          <ol className="grid gap-4 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="flex gap-3.5 rounded-2xl border border-slate-200 bg-white p-5">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
                  <Icon className="size-6" />
                </span>
                <div>
                  <h3 className="font-bold text-slate-900">
                    <span className="sr-only">Step {i + 1}: </span>
                    {title}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-600">{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="ops" className="flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="flex items-start gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
              <Truck className="size-6" />
            </span>
            <div>
              <h2 id="ops" className="text-lg font-bold text-slate-900">
                Running a bus, kombi or truck?
              </h2>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-600">
                Plan up to five stops, check hazards along the whole trip and print a one-page driver briefing.
              </p>
            </div>
          </div>
          <Button asChild variant="outline" size="lg">
            <Link href="/public/operators">
              Open the multi-stop planner <ArrowRight />
            </Link>
          </Button>
        </section>

        <section id="about" aria-labelledby="about-h" className="max-w-2xl scroll-mt-24 space-y-2 text-[15px] leading-relaxed text-slate-700">
          <h2 id="about-h" className="text-lg font-bold text-slate-900">
            About SafeRouteZW
          </h2>
          <p>
            SafeRouteZW collects road incident reports from news and official sources. A human editor reviews each report and
            decides whether to publish it. Only published notices appear here.
          </p>
          <p>
            Notices can be incomplete, delayed or out of date, and locations may be approximate. Route times are estimates
            without live traffic. If no alert appears on your route, that is not proof the road is safe.
          </p>
        </section>
      </Container>
    </>
  );
}
