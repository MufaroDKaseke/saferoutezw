import Link from "next/link";
import { Suspense } from "react";
import { ArrowRight, Bell, Clock, FileSearch, Inbox, ListChecks, Map as MapIcon, ShieldCheck, Truck } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { JourneyForm } from "@/components/public/journey-form";
import { RouteArt } from "@/components/public/route-art";
import { Container, EmptyState } from "@/components/public/site-chrome";
import { ErrorNotice } from "@/components/public/error-notice";
import { SubscribeBand } from "@/components/public/subscribe-cta";
import { Button } from "@/components/ui/button";
import { PageFallback } from "@/components/public/page-fallback";
import { Skeleton } from "@/components/ui/skeleton";
import { getI18n } from "@/lib/i18n/server";
import type { TranslationKey } from "@/lib/i18n/translate";
import { attempt, describeError, formatWhen, publicApi } from "@/lib/public-api/client";

const QUICK_ACTIONS: ReadonlyArray<{ href: string; label: TranslationKey; text: TranslationKey; icon: typeof ListChecks }> = [
  { href: "/public/alerts", label: "nav.alerts", text: "home.quick.alerts", icon: ListChecks },
  { href: "/public/map", label: "nav.map", text: "home.quick.map", icon: MapIcon },
  { href: "/public/subscribe", label: "home.quick.subscribeTitle", text: "home.quick.subscribe", icon: Bell },
  { href: "/public/operators", label: "nav.operators", text: "home.quick.operators", icon: Truck },
];

const STEPS: ReadonlyArray<{ icon: typeof FileSearch; title: TranslationKey; text: TranslationKey }> = [
  { icon: FileSearch, title: "home.how.gatheredTitle", text: "home.how.gathered" },
  { icon: ShieldCheck, title: "home.how.reviewTitle", text: "home.how.review" },
  { icon: Bell, title: "home.how.informedTitle", text: "home.how.informed" },
];

async function Hero() {
  const { t } = await getI18n();
  return (
    <section className="relative overflow-hidden bg-slate-900 text-white">
      <Container className="grid items-center gap-8 py-10 sm:py-14 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:py-16">
        <div className="space-y-5">
          <p className="text-sm font-semibold text-emerald-300">{t("home.eyebrow")}</p>
          <h1 className="text-5xl font-extrabold tracking-tight text-balance sm:text-6xl">{t("home.title")}</h1>
          <p className="max-w-lg text-lg leading-relaxed text-slate-300">{t("home.lead")}</p>
          <JourneyForm />
          <p className="flex items-center gap-2 text-sm text-slate-300">
            <ShieldCheck className="size-4 shrink-0 text-emerald-400" aria-hidden />
            {t("home.reviewedNote")}
          </p>
        </div>
        <RouteArt className="h-44 overflow-hidden rounded-3xl ring-1 ring-white/10 sm:h-64 lg:h-[30rem]" />
      </Container>
    </section>
  );
}

async function QuickActions() {
  const { t } = await getI18n();
  return (
    <nav aria-label={t("home.quickActions")} className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
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
            <span className="block text-base font-bold text-slate-900 group-hover:underline">{t(label)}</span>
            <span className="block text-[13px] leading-snug text-slate-600 sm:text-sm">{t(text)}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}

function LatestSkeleton({ label }: { label: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2" role="status" aria-label={label}>
      {[0, 1].map((i) => (
        <Skeleton key={i} className="h-40 rounded-2xl" />
      ))}
    </div>
  );
}

async function LatestAlerts() {
  const { t, rich, locale } = await getI18n();
  const { data: summary, error } = await attempt(() => publicApi.summary());
  if (error) return <ErrorNotice message={describeError(error, t)} />;
  const count = summary.recent_alert_count;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-slate-200 bg-white px-5 py-4">
        <p className="text-sm text-slate-700">
          {rich(
            "home.latest.count",
            { b: (c) => <strong className="mr-1 text-2xl font-extrabold tracking-tight text-slate-900 tnum">{c}</strong> },
            { count, days: summary.window_days },
          )}
        </p>
        {summary.last_updated ? (
          <p className="flex items-center gap-1.5 text-sm text-slate-600">
            <Clock className="size-4" aria-hidden /> {t("home.latest.lastUpdate", { when: formatWhen(summary.last_updated, locale) })}
          </p>
        ) : null}
      </div>
      {summary.latest_alerts.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={t("home.latest.empty")}
          actions={
            <>
              <Button asChild variant="approve" size="lg">
                <Link href="/public/subscribe">
                  <Bell /> {t("home.latest.tellMe")}
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/public/map">{t("home.latest.openMap")}</Link>
              </Button>
            </>
          }
        >
          {t("home.latest.emptyBody")}
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

async function HomeContent() {
  const { t } = await getI18n();
  return (
    <>
      <Hero />
      <Container className="space-y-14 py-8 sm:space-y-16 sm:py-12">
        <QuickActions />

        <section aria-labelledby="latest" className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="latest" className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
              {t("home.latest.title")}
            </h2>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">
                {t("home.latest.viewAll")} <ArrowRight />
              </Link>
            </Button>
          </div>
          <Suspense fallback={<LatestSkeleton label={t("home.latest.loading")} />}>
            <LatestAlerts />
          </Suspense>
        </section>

        <SubscribeBand />

        <section id="how" aria-labelledby="how-h" className="scroll-mt-24 space-y-5">
          <h2 id="how-h" className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            {t("home.how.title")}
          </h2>
          <ol className="grid gap-4 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="flex gap-3.5 rounded-2xl border border-slate-200 bg-white p-5">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
                  <Icon className="size-6" />
                </span>
                <div>
                  <h3 className="font-bold text-slate-900">
                    <span className="sr-only">{t("home.how.step", { n: i + 1 })}</span>
                    {t(title)}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-600">{t(text)}</p>
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
                {t("home.ops.title")}
              </h2>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-slate-600">{t("home.ops.body")}</p>
            </div>
          </div>
          <Button asChild variant="outline" size="lg">
            <Link href="/public/operators">
              {t("home.ops.cta")} <ArrowRight />
            </Link>
          </Button>
        </section>

        <section id="about" aria-labelledby="about-h" className="max-w-2xl scroll-mt-24 space-y-2 text-[15px] leading-relaxed text-slate-700">
          <h2 id="about-h" className="text-lg font-bold text-slate-900">
            {t("home.about.title")}
          </h2>
          <p>{t("home.about.p1")}</p>
          <p>{t("home.about.p2")}</p>
        </section>
      </Container>
    </>
  );
}

export default function PublicHome() {
  return (
    <Suspense fallback={<PageFallback />}>
      <HomeContent />
    </Suspense>
  );
}
