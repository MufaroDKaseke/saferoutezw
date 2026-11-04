import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Bell, ChevronLeft, ChevronRight, Inbox, Map as MapIcon, Search, SlidersHorizontal, X } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { ErrorNotice } from "@/components/public/error-notice";
import { SeverityBadge } from "@/components/public/hazard";
import { EmptyState, Notice, PageShell } from "@/components/public/site-chrome";
import { SubscribeCard } from "@/components/public/subscribe-cta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";
import type { Translator } from "@/lib/i18n/translate";
import { HAZARD_LABELS, PROVINCES, attempt, describeError, publicApi } from "@/lib/public-api/client";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.alerts.title") };
}

const PAGE_SIZE = 10;
type SP = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

const CONTROL =
  "h-12 w-full rounded-xl border border-input bg-white px-3 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

const FILTER_KEYS = ["province", "hazard_type", "road"] as const;

function queryString(sp: SP, overrides: Record<string, string | null> = {}) {
  const params = new URLSearchParams();
  for (const key of ["q", ...FILTER_KEYS]) if (one(sp[key])) params.set(key, one(sp[key]));
  for (const [k, v] of Object.entries(overrides)) {
    if (v === null) params.delete(k);
    else params.set(k, v);
  }
  const s = params.toString();
  return s ? `/public/alerts?${s}` : "/public/alerts";
}

/**
 * A plain GET form: it works without JavaScript and keeps the page light. Search stays in view; the
 * other filters sit in a disclosure that opens by itself when one is active.
 */
function Filters({ sp, t, maybe }: { sp: SP; t: Translator["t"]; maybe: Translator["maybe"] }) {
  const active = FILTER_KEYS.filter((k) => one(sp[k]));
  return (
    <form method="get" role="search" aria-label={t("alerts.searchForm")} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex gap-2">
        <label className="relative flex-1">
          <span className="sr-only">{t("alerts.searchLabel")}</span>
          <Search className="pointer-events-none absolute top-3.5 left-3.5 size-5 text-slate-500" aria-hidden />
          <input name="q" defaultValue={one(sp.q)} maxLength={100} placeholder={t("alerts.searchPlaceholder")} className={`${CONTROL} pl-11`} />
        </label>
        <Button type="submit" variant="approve" size="lg" className="h-12 px-5 text-base">
          <span className="sr-only sm:not-sr-only">{t("alerts.search")}</span>
          <Search className="sm:hidden" aria-hidden />
        </Button>
      </div>

      <details className="group" open={active.length > 0}>
        <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 rounded-lg px-1 text-sm font-semibold text-slate-800 select-none hover:text-slate-950 [&::-webkit-details-marker]:hidden">
          <SlidersHorizontal className="size-4" aria-hidden />
          {active.length ? t("alerts.filtersCount", { count: active.length }) : t("alerts.filters")}
          <ChevronRight className="size-4 transition-transform group-open:rotate-90" aria-hidden />
        </summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 text-sm font-semibold">
            {t("alerts.province")}
            <select name="province" defaultValue={one(sp.province)} className={CONTROL}>
              <option value="">{t("alerts.allProvinces")}</option>
              {PROVINCES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            {t("alerts.hazardType")}
            <select name="hazard_type" defaultValue={one(sp.hazard_type)} className={CONTROL}>
              <option value="">{t("alerts.allTypes")}</option>
              {Object.keys(HAZARD_LABELS).map((value) => (
                <option key={value} value={value}>
                  {maybe(`hazard.${value}`) ?? value}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            {t("alerts.road")}
            <input name="road" defaultValue={one(sp.road)} maxLength={100} className={CONTROL} placeholder={t("alerts.roadPlaceholder")} />
          </label>
          <div className="flex gap-2 sm:col-span-3">
            <Button type="submit" size="lg">
              {t("alerts.apply")}
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">{t("alerts.clear")}</Link>
            </Button>
          </div>
        </div>
      </details>
    </form>
  );
}

function ActiveFilters({ sp, t, maybe }: { sp: SP; t: Translator["t"]; maybe: Translator["maybe"] }) {
  const chips: Array<{ key: string; label: string }> = [];
  if (one(sp.q)) chips.push({ key: "q", label: t("alerts.chip.search", { value: one(sp.q) }) });
  if (one(sp.province)) chips.push({ key: "province", label: one(sp.province) });
  if (one(sp.hazard_type)) chips.push({ key: "hazard_type", label: maybe(`hazard.${one(sp.hazard_type)}`) ?? one(sp.hazard_type) });
  if (one(sp.road)) chips.push({ key: "road", label: t("alerts.chip.road", { value: one(sp.road) }) });
  if (!chips.length) return null;
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label={t("alerts.active")}>
      {chips.map((c) => (
        <li key={c.key}>
          <Link
            href={queryString(sp, { [c.key]: null, page: null })}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-700"
          >
            {c.label}
            <X className="size-3.5" aria-hidden />
            <span className="sr-only">{t("alerts.removeFilter")}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

async function Results({ searchParams }: { searchParams: Promise<SP> }) {
  const { t } = await getI18n();
  const sp = await searchParams;
  const page = Math.max(1, Number.parseInt(one(sp.page), 10) || 1);
  const { data, error } = await attempt(() =>
    publicApi.alerts({
      page,
      page_size: PAGE_SIZE,
      q: one(sp.q) || undefined,
      province: one(sp.province) || undefined,
      road: one(sp.road) || undefined,
      hazard_type: one(sp.hazard_type) || undefined,
    }),
  );
  if (error) return <ErrorNotice message={describeError(error, t)} />;
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const link = (p: number) => queryString(sp, { page: String(p) });
  const filtered = Boolean(one(sp.q) || one(sp.province) || one(sp.road) || one(sp.hazard_type));
  const pager = "inline-flex min-h-11 items-center gap-1 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-900 hover:bg-slate-100";
  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-slate-800" aria-live="polite">
        {t("alerts.count", { count: data.total })}
        <span className="ml-2 font-normal text-slate-600">{t("alerts.newestFirst")}</span>
      </p>
      {data.items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={filtered ? t("alerts.noMatch") : t("alerts.none")}
          actions={
            <>
              {filtered ? (
                <Button asChild variant="approve" size="lg">
                  <Link href="/public/alerts">{t("alerts.clearFilters")}</Link>
                </Button>
              ) : null}
              <Button asChild variant="outline" size="lg">
                <Link href="/public/subscribe">
                  <Bell /> {t("common.getAlerts")}
                </Link>
              </Button>
            </>
          }
        >
          {filtered ? t("alerts.widerArea") : ""}
          {t("alerts.noneNotSafe")}
        </EmptyState>
      ) : (
        data.items.map((a) => <AlertCard key={a.id} alert={a} />)
      )}
      {pages > 1 ? (
        <nav aria-label={t("alerts.pagination")} className="flex items-center justify-between gap-3 pt-2">
          {page > 1 ? (
            <Link href={link(page - 1)} className={pager} rel="prev">
              <ChevronLeft className="size-4" aria-hidden /> {t("alerts.previous")}
            </Link>
          ) : (
            <span />
          )}
          <span className="text-sm text-slate-600">{t("alerts.pageOf", { page, pages })}</span>
          {page < pages ? (
            <Link href={link(page + 1)} className={pager} rel="next">
              {t("alerts.next")} <ChevronRight className="size-4" aria-hidden />
            </Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </div>
  );
}

function SeverityGuide({ t }: { t: Translator["t"] }) {
  return (
    <section aria-labelledby="sev-guide" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 id="sev-guide" className="font-bold text-slate-900">
        {t("severity.guide")}
      </h2>
      <ul className="space-y-3">
        {(["fatal", "serious", "minor"] as const).map((k) => (
          <li key={k} className="space-y-1">
            <SeverityBadge severity={k} />
            <p className="text-[13px] leading-snug text-slate-600">{t(`severity.${k}.meaning`)}</p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500">{t("severity.setByEditor")}</p>
    </section>
  );
}

function ResultsSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-4" role="status" aria-label={label}>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-36 rounded-2xl" />
      ))}
    </div>
  );
}

async function FiltersAndResults({ searchParams }: { searchParams: Promise<SP> }) {
  const { t, maybe } = await getI18n();
  const sp = await searchParams;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="space-y-4">
        <Filters sp={sp} t={t} maybe={maybe} />
        <ActiveFilters sp={sp} t={t} maybe={maybe} />
        <Suspense fallback={<ResultsSkeleton label={t("alerts.loading")} />}>
          <Results searchParams={searchParams} />
        </Suspense>
      </div>
      <aside className="space-y-4 lg:pt-0" aria-label={t("alerts.aboutAside")}>
        <SubscribeCard />
        <SeverityGuide t={t} />
        <Notice tone="warning" role="note">
          {t("common.noAlertNotSafe")} {t("common.followPolice")}
        </Notice>
        <Button asChild variant="outline" size="lg" className="w-full">
          <Link href="/public/map">
            <MapIcon /> {t("alerts.viewOnMap")}
          </Link>
        </Button>
      </aside>
    </div>
  );
}

async function AlertsContent({ searchParams }: { searchParams: Promise<SP> }) {
  const { t } = await getI18n();
  return (
    <PageShell title={t("alerts.title")} intro={t("alerts.intro")}>
      <Suspense fallback={<ResultsSkeleton label={t("alerts.loading")} />}>
        <FiltersAndResults searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}

export default function AlertsPage({ searchParams }: { searchParams: Promise<SP> }) {
  return (
    <Suspense fallback={<PageFallback />}>
      <AlertsContent searchParams={searchParams} />
    </Suspense>
  );
}
