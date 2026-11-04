import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ErrorNotice } from "@/components/public/error-notice";
import { LoadingText } from "@/components/public/loading-text";
import { PageFallback } from "@/components/public/page-fallback";
import { PageShell } from "@/components/public/site-chrome";
import { formatFigure, subtypeLabel } from "@/lib/domain/intelligence";
import { intlTag } from "@/lib/i18n/config";
import { getI18n } from "@/lib/i18n/server";
import type { Translator } from "@/lib/i18n/translate";
import { attempt, describeError, formatWhen, publicApi } from "@/lib/public-api/client";
import { PRIMARY_CATEGORIES, type PrimaryCategory } from "@/lib/taxonomy.generated";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.transport.title") };
}

type SP = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

/** Category name in the reader's language. Sub-types (about a hundred terms) are shown as the API names them. */
const categoryName = ({ maybe }: Translator, key: string) => maybe(`category.${key}`) ?? key;

/** "4 Nov 2026" in the reader's language, with the same year-only shortcut the newsroom uses. */
function formatPeriod({ t, locale }: Translator, start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return t("transport.periodNotStated");
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString(intlTag(locale), { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  if (start && end) {
    if (start.endsWith("-01-01") && end.endsWith("-12-31") && start.slice(0, 4) === end.slice(0, 4)) return start.slice(0, 4);
    return start === end ? fmt(start) : t("transport.periodRange", { start: fmt(start), end: fmt(end) });
  }
  return fmt((start ?? end) as string);
}

async function News({ category }: { category: string }) {
  const i18n = await getI18n();
  const { t, locale } = i18n;
  const { data, error } = await attempt(() => publicApi.transportNews({ category: category || undefined, page_size: 10 }));
  if (error) return <ErrorNotice message={describeError(error, t)} />;
  if (data.items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
        {t("transport.noNews")}
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {data.items.map((item) => (
        <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold text-slate-600">
            {categoryName(i18n, item.category)}
            {item.subtype ? ` · ${subtypeLabel(item.subtype)}` : ""}
          </p>
          <h3 className="mt-1 text-base font-semibold text-slate-900">{item.headline}</h3>
          <p className="mt-1 text-sm text-slate-700">{item.summary}</p>
          <p className="mt-2 text-xs text-slate-600">
            {t("transport.publishedAt", { when: formatWhen(item.published_at, locale) })}
            {item.source_attribution ? t("transport.reportedBy", { name: item.source_attribution }) : ""}
          </p>
          {item.sources.length > 0 ? (
            <p className="mt-1 text-xs text-slate-600">
              {t("common.source")}
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
  const i18n = await getI18n();
  const { t } = i18n;
  const { data, error } = await attempt(() => publicApi.transportStatistics({ limit: 50 }));
  if (error) return <ErrorNotice message={describeError(error, t)} />;
  if (data.statistics.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
        {t("transport.noFigures")}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-600">{data.note}</p>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <caption className="sr-only">{t("transport.tableCaption")}</caption>
          <thead className="text-left text-xs text-slate-600">
            <tr>
              <th className="p-3">{t("transport.colFigure")}</th>
              <th className="p-3">{t("transport.colPeriod")}</th>
              <th className="p-3">{t("transport.colCoverage")}</th>
              <th className="p-3">{t("transport.colSource")}</th>
            </tr>
          </thead>
          <tbody>
            {data.statistics.map((s) => (
              <tr key={`${s.published_item_id}${s.metric}${s.period_start}`} className="border-t align-top">
                <td className="p-3">
                  <strong>{formatFigure(s.value, s.unit)}</strong>
                  <br />
                  {s.metric}
                  {s.is_preliminary ? <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">{t("transport.preliminary")}</span> : null}
                </td>
                <td className="p-3">{formatPeriod(i18n, s.period_start, s.period_end)}</td>
                <td className="p-3">{s.geographic_coverage ?? t("common.notStated")}</td>
                <td className="p-3">
                  {s.source_reference ?? t("common.notStated")}
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
  const { t, locale } = await getI18n();
  const { data, error } = await attempt(() => publicApi.transportInsights({ page_size: 5 }));
  if (error) return <ErrorNotice message={describeError(error, t)} />;
  if (data.items.length === 0) return <p className="text-sm text-slate-600">{t("transport.noInsights")}</p>;
  return (
    <ul className="space-y-3">
      {data.items.map((item) => (
        <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-base font-semibold">{item.headline}</h3>
          <p className="mt-1 text-sm text-slate-700">{item.summary}</p>
          <p className="mt-2 text-xs text-slate-600">{t("transport.publishedAt", { when: formatWhen(item.published_at, locale) })}</p>
        </li>
      ))}
    </ul>
  );
}

async function TransportContent({ searchParams }: { searchParams: Promise<SP> }) {
  const i18n = await getI18n();
  const { t } = i18n;
  const sp = await searchParams;
  const category = one(sp.category);
  return (
    <PageShell title={t("transport.title")} intro={t("transport.intro")}>
      <div className="space-y-10">
        <section className="space-y-3" aria-labelledby="news">
          <h2 id="news" className="text-xl font-semibold text-slate-900">
            {t("transport.news")}
          </h2>
          <nav aria-label={t("transport.filterTopic")} className="flex flex-wrap gap-2">
            <Link href="/public/transport" aria-current={category ? undefined : "page"} className="rounded-full border px-3 py-1.5 text-sm font-medium aria-[current=page]:bg-slate-900 aria-[current=page]:text-white">
              {t("transport.allTopics")}
            </Link>
            {PRIMARY_CATEGORIES.filter((c: PrimaryCategory) => c !== "other_transport_intelligence").map((c: PrimaryCategory) => (
              <Link
                key={c}
                href={`/public/transport?category=${c}`}
                aria-current={category === c ? "page" : undefined}
                className="rounded-full border px-3 py-1.5 text-sm font-medium aria-[current=page]:bg-slate-900 aria-[current=page]:text-white"
              >
                {categoryName(i18n, c)}
              </Link>
            ))}
          </nav>
          <Suspense fallback={<LoadingText />}>
            <News category={category} />
          </Suspense>
        </section>

        <section className="space-y-3" aria-labelledby="stats">
          <h2 id="stats" className="text-xl font-semibold text-slate-900">
            {t("transport.figures")}
          </h2>
          <Suspense fallback={<LoadingText />}>
            <Statistics />
          </Suspense>
        </section>

        <section className="space-y-3" aria-labelledby="insights">
          <h2 id="insights" className="text-xl font-semibold text-slate-900">
            {t("transport.insights")}
          </h2>
          <Suspense fallback={<LoadingText />}>
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
    <Suspense fallback={<PageFallback />}>
      <TransportContent searchParams={searchParams} />
    </Suspense>
  );
}
