import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ErrorNotice, PageShell } from "@/components/public/site-chrome";
import { categoryLabel, formatFigure, formatPeriod, subtypeLabel } from "@/lib/domain/intelligence";
import { attempt, formatWhen, publicApi } from "@/lib/public-api/client";
import { CATEGORY_LABELS, PRIMARY_CATEGORIES } from "@/lib/taxonomy.generated";

export const metadata: Metadata = { title: "Transport news and road safety figures" };

type SP = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

async function News({ category }: { category: string }) {
  const { data, error } = await attempt(() => publicApi.transportNews({ category: category || undefined, page_size: 10 }));
  if (error) return <ErrorNotice message={error.message} />;
  if (data.items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
        No transport news has been published yet.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {data.items.map((item) => (
        <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold text-slate-600">
            {categoryLabel(item.category)}
            {item.subtype ? ` · ${subtypeLabel(item.subtype)}` : ""}
          </p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">{item.headline}</h3>
          <p className="mt-1 text-sm text-slate-700">{item.summary}</p>
          <p className="mt-2 text-xs text-slate-600">
            Published {formatWhen(item.published_at)}
            {item.source_attribution ? ` · Reported by ${item.source_attribution}` : ""}
          </p>
          {item.sources.length > 0 ? (
            <p className="mt-1 text-xs text-slate-600">
              Source:{" "}
              {item.sources.map((s, i) => (
                <span key={s.name}>
                  {i > 0 ? ", " : ""}
                  {s.url ? (
                    <a href={s.url} rel="noreferrer noopener" target="_blank" className="underline">
                      {s.name}
                    </a>
                  ) : (
                    s.name
                  )}
                </span>
              ))}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

async function Statistics() {
  const { data, error } = await attempt(() => publicApi.transportStatistics({ limit: 50 }));
  if (error) return <ErrorNotice message={error.message} />;
  if (data.statistics.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
        No verified road safety figures have been published yet.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-600">{data.note}</p>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <caption className="sr-only">Published road safety figures with reporting period and source</caption>
          <thead className="text-left text-xs text-slate-600">
            <tr>
              <th className="p-3">Figure</th>
              <th className="p-3">Reporting period</th>
              <th className="p-3">Coverage</th>
              <th className="p-3">Source</th>
            </tr>
          </thead>
          <tbody>
            {data.statistics.map((s) => (
              <tr key={`${s.published_item_id}${s.metric}${s.period_start}`} className="border-t align-top">
                <td className="p-3">
                  <strong>{formatFigure(s.value, s.unit)}</strong>
                  <br />
                  {s.metric}
                  {s.is_preliminary ? <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">Preliminary</span> : null}
                </td>
                <td className="p-3">{formatPeriod(s.period_start, s.period_end)}</td>
                <td className="p-3">{s.geographic_coverage ?? "Not stated"}</td>
                <td className="p-3">
                  {s.source_reference ?? "Not stated"}
                  {s.methodology ? <span className="block text-xs text-slate-600">{s.methodology}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

async function Insights() {
  const { data, error } = await attempt(() => publicApi.transportInsights({ page_size: 5 }));
  if (error) return <ErrorNotice message={error.message} />;
  if (data.items.length === 0) return <p className="text-sm text-slate-600">No reports or insights have been published yet.</p>;
  return (
    <ul className="space-y-3">
      {data.items.map((item) => (
        <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-base font-semibold">{item.headline}</h3>
          <p className="mt-1 text-sm text-slate-700">{item.summary}</p>
          <p className="mt-2 text-xs text-slate-600">Published {formatWhen(item.published_at)}</p>
        </li>
      ))}
    </ul>
  );
}

async function TransportContent({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const category = one(sp.category);
  return (
    <PageShell
      title="Transport news and road safety figures"
      intro="Reviewed reports about roads, public transport, freight and road safety in Zimbabwe. This is separate from road hazard alerts, which are listed under Alerts."
    >
      <div className="space-y-10">
        <section className="space-y-3" aria-labelledby="news">
          <h2 id="news" className="text-xl font-semibold text-slate-900">
            Transport news
          </h2>
          <nav aria-label="Filter by topic" className="flex flex-wrap gap-2">
            <Link href="/public/transport" aria-current={category ? undefined : "page"} className="rounded-full border px-3 py-1.5 text-sm font-medium aria-[current=page]:bg-slate-900 aria-[current=page]:text-white">
              All topics
            </Link>
            {PRIMARY_CATEGORIES.filter((c) => c !== "other_transport_intelligence").map((c) => (
              <Link
                key={c}
                href={`/public/transport?category=${c}`}
                aria-current={category === c ? "page" : undefined}
                className="rounded-full border px-3 py-1.5 text-sm font-medium aria-[current=page]:bg-slate-900 aria-[current=page]:text-white"
              >
                {CATEGORY_LABELS[c]}
              </Link>
            ))}
          </nav>
          <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
            <News category={category} />
          </Suspense>
        </section>

        <section className="space-y-3" aria-labelledby="stats">
          <h2 id="stats" className="text-xl font-semibold text-slate-900">
            Road safety figures
          </h2>
          <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
            <Statistics />
          </Suspense>
        </section>

        <section className="space-y-3" aria-labelledby="insights">
          <h2 id="insights" className="text-xl font-semibold text-slate-900">
            Reports and insights
          </h2>
          <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
            <Insights />
          </Suspense>
        </section>
      </div>
    </PageShell>
  );
}

/** searchParams is request-time data, so it is read inside a Suspense boundary (Cache Components). */
export default function TransportPage({ searchParams }: { searchParams: Promise<SP> }) {
  return (
    <Suspense fallback={<p className="px-4 py-8 text-sm text-slate-500">Loading…</p>}>
      <TransportContent searchParams={searchParams} />
    </Suspense>
  );
}
