import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { AlertCard } from "@/components/public/alert-card";
import { ErrorNotice, PageShell } from "@/components/public/site-chrome";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HAZARD_LABELS, PROVINCES, attempt, publicApi } from "@/lib/public-api/client";

export const metadata: Metadata = { title: "Road alerts" };

const PAGE_SIZE = 10;
type SP = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

const SELECT =
  "h-11 w-full rounded-lg border border-input bg-white px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

/** A plain GET form: works without JavaScript and keeps the page light. */
function Filters({ sp }: { sp: SP }) {
  return (
    <form method="get" className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2">
      <label className="grid gap-1 text-sm font-medium sm:col-span-2">
        Search
        <Input name="q" defaultValue={one(sp.q)} maxLength={100} className="h-11" placeholder="Road, town or keyword" />
      </label>
      <label className="grid gap-1 text-sm font-medium">
        Province
        <select name="province" defaultValue={one(sp.province)} className={SELECT}>
          <option value="">All provinces</option>
          {PROVINCES.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm font-medium">
        Hazard type
        <select name="hazard_type" defaultValue={one(sp.hazard_type)} className={SELECT}>
          <option value="">All types</option>
          {Object.entries(HAZARD_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm font-medium sm:col-span-2">
        Road or route
        <Input name="road" defaultValue={one(sp.road)} maxLength={100} className="h-11" placeholder="e.g. A3 or Harare-Mutare" />
      </label>
      <div className="flex gap-3 sm:col-span-2">
        <Button type="submit" size="lg">Apply filters</Button>
        <Button asChild variant="outline" size="lg">
          <Link href="/public/alerts">Clear</Link>
        </Button>
      </div>
    </form>
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
  const link = (p: number) => {
    const params = new URLSearchParams();
    for (const key of ["q", "province", "road", "hazard_type"]) if (one(sp[key])) params.set(key, one(sp[key]));
    params.set("page", String(p));
    return `/public/alerts?${params}`;
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600" aria-live="polite">
        {data.total} published notice{data.total === 1 ? "" : "s"}
      </p>
      {data.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
          No published notices match. This does not mean the road is safe.
        </p>
      ) : (
        data.items.map((a) => <AlertCard key={a.id} alert={a} />)
      )}
      {pages > 1 ? (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
          {page > 1 ? (
            <Button asChild variant="outline" size="lg"><Link href={link(page - 1)}>Previous</Link></Button>
          ) : <span />}
          <span className="text-sm text-slate-600">Page {page} of {pages}</span>
          {page < pages ? (
            <Button asChild variant="outline" size="lg"><Link href={link(page + 1)}>Next</Link></Button>
          ) : <span />}
        </nav>
      ) : null}
    </div>
  );
}

async function FiltersAndResults({ searchParams }: { searchParams: Promise<SP> }) {
  return (
    <>
      <Filters sp={await searchParams} />
      <Results searchParams={searchParams} />
    </>
  );
}

export default function AlertsPage({ searchParams }: { searchParams: Promise<SP> }) {
  return (
    <PageShell title="Road alerts" intro="Notices reviewed and published by SafeRouteZW editors, newest first.">
      <Suspense fallback={<p className="text-sm text-slate-500">Loading alerts…</p>}>
        <FiltersAndResults searchParams={searchParams} />
      </Suspense>
    </PageShell>
  );
}
