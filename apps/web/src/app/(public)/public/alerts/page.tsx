import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Bell, ChevronLeft, ChevronRight, Inbox, Map as MapIcon, Search, SlidersHorizontal, X } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { SeverityBadge } from "@/components/public/hazard";
import { EmptyState, ErrorNotice, Notice, PageShell } from "@/components/public/site-chrome";
import { SubscribeCard } from "@/components/public/subscribe-cta";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { HAZARD_LABELS, PROVINCES, attempt, publicApi } from "@/lib/public-api/client";
import { SEVERITY } from "@/lib/public-api/hazard-style";

export const metadata: Metadata = { title: "Road alerts" };

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
function Filters({ sp }: { sp: SP }) {
  const active = FILTER_KEYS.filter((k) => one(sp[k]));
  return (
    <form method="get" role="search" aria-label="Search and filter road alerts" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex gap-2">
        <label className="relative flex-1">
          <span className="sr-only">Search alerts</span>
          <Search className="pointer-events-none absolute top-3.5 left-3.5 size-5 text-slate-500" aria-hidden />
          <input name="q" defaultValue={one(sp.q)} maxLength={100} placeholder="Road, town or keyword" className={`${CONTROL} pl-11`} />
        </label>
        <Button type="submit" variant="approve" size="lg" className="h-12 px-5 text-base">
          <span className="sr-only sm:not-sr-only">Search</span>
          <Search className="sm:hidden" aria-hidden />
        </Button>
      </div>

      <details className="group" open={active.length > 0}>
        <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 rounded-lg px-1 text-sm font-semibold text-slate-800 select-none hover:text-slate-950 [&::-webkit-details-marker]:hidden">
          <SlidersHorizontal className="size-4" aria-hidden />
          Filters{active.length ? ` (${active.length})` : ""}
          <ChevronRight className="size-4 transition-transform group-open:rotate-90" aria-hidden />
        </summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 text-sm font-semibold">
            Province
            <select name="province" defaultValue={one(sp.province)} className={CONTROL}>
              <option value="">All provinces</option>
              {PROVINCES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            Hazard type
            <select name="hazard_type" defaultValue={one(sp.hazard_type)} className={CONTROL}>
              <option value="">All types</option>
              {Object.entries(HAZARD_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            Road or route
            <input name="road" defaultValue={one(sp.road)} maxLength={100} className={CONTROL} placeholder="e.g. A3 or Harare-Mutare" />
          </label>
          <div className="flex gap-2 sm:col-span-3">
            <Button type="submit" size="lg">
              Apply filters
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">Clear</Link>
            </Button>
          </div>
        </div>
      </details>
    </form>
  );
}

function ActiveFilters({ sp }: { sp: SP }) {
  const chips: Array<{ key: string; label: string }> = [];
  if (one(sp.q)) chips.push({ key: "q", label: `Search: ${one(sp.q)}` });
  if (one(sp.province)) chips.push({ key: "province", label: one(sp.province) });
  if (one(sp.hazard_type)) chips.push({ key: "hazard_type", label: HAZARD_LABELS[one(sp.hazard_type)] ?? one(sp.hazard_type) });
  if (one(sp.road)) chips.push({ key: "road", label: `Road: ${one(sp.road)}` });
  if (!chips.length) return null;
  return (
    <ul className="flex flex-wrap items-center gap-2" aria-label="Active filters">
      {chips.map((c) => (
        <li key={c.key}>
          <Link
            href={queryString(sp, { [c.key]: null, page: null })}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-700"
          >
            {c.label}
            <X className="size-3.5" aria-hidden />
            <span className="sr-only">Remove filter</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

async function Results({ searchParams }: { searchParams: Promise<SP> }) {
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
  if (error) return <ErrorNotice message={error.message} />;
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const link = (p: number) => queryString(sp, { page: String(p) });
  const filtered = Boolean(one(sp.q) || one(sp.province) || one(sp.road) || one(sp.hazard_type));
  const pager = "inline-flex min-h-11 items-center gap-1 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-900 hover:bg-slate-100";
  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-slate-800" aria-live="polite">
        {data.total} published notice{data.total === 1 ? "" : "s"}
        <span className="ml-2 font-normal text-slate-600">Newest first</span>
      </p>
      {data.items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={filtered ? "No published notices match" : "There are no published notices right now"}
          actions={
            <>
              {filtered ? (
                <Button asChild variant="approve" size="lg">
                  <Link href="/public/alerts">Clear filters</Link>
                </Button>
              ) : null}
              <Button asChild variant="outline" size="lg">
                <Link href="/public/subscribe">
                  <Bell /> Get alerts
                </Link>
              </Button>
            </>
          }
        >
          {filtered ? "Try a wider area or remove a filter. " : ""}No notices does not mean the road is free of hazards.
        </EmptyState>
      ) : (
        data.items.map((a) => <AlertCard key={a.id} alert={a} />)
      )}
      {pages > 1 ? (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3 pt-2">
          {page > 1 ? (
            <Link href={link(page - 1)} className={pager} rel="prev">
              <ChevronLeft className="size-4" aria-hidden /> Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="text-sm text-slate-600">
            Page {page} of {pages}
          </span>
          {page < pages ? (
            <Link href={link(page + 1)} className={pager} rel="next">
              Next <ChevronRight className="size-4" aria-hidden />
            </Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </div>
  );
}

function SeverityGuide() {
  return (
    <section aria-labelledby="sev-guide" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 id="sev-guide" className="font-bold text-slate-900">
        Severity guide
      </h2>
      <ul className="space-y-3">
        {(["fatal", "serious", "minor"] as const).map((k) => (
          <li key={k} className="space-y-1">
            <SeverityBadge severity={k} />
            <p className="text-[13px] leading-snug text-slate-600">{SEVERITY[k].meaning}</p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500">Severity is set by the editor who approves each notice.</p>
    </section>
  );
}

function ResultsSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading alerts">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-36 rounded-2xl" />
      ))}
    </div>
  );
}

async function FiltersAndResults({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="space-y-4">
        <Filters sp={sp} />
        <ActiveFilters sp={sp} />
        <Suspense fallback={<ResultsSkeleton />}>
          <Results searchParams={searchParams} />
        </Suspense>
      </div>
      <aside className="space-y-4 lg:pt-0" aria-label="About these alerts">
        <SubscribeCard />
        <SeverityGuide />
        <Notice tone="warning" role="note">
          No alert on your route does not mean the road is safe. Follow police and traffic authority instructions.
        </Notice>
        <Button asChild variant="outline" size="lg" className="w-full">
          <Link href="/public/map">
            <MapIcon /> View on the map
          </Link>
        </Button>
      </aside>
    </div>
  );
}

export default function AlertsPage({ searchParams }: { searchParams: Promise<SP> }) {
  return (
    <PageShell title="Road alerts" intro="Notices reviewed and published by SafeRouteZW editors, newest first.">
      <Suspense fallback={<ResultsSkeleton />}>
        <FiltersAndResults searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}
