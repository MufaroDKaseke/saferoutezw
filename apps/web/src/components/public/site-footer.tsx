import Link from "next/link";
import { BrandMark, Wordmark } from "@/components/layout/brand";
import { LanguageSwitcher } from "@/components/public/language-switcher";
import { Container } from "@/components/public/site-chrome";
import { getI18n } from "@/lib/i18n/server";
import type { TranslationKey } from "@/lib/i18n/translate";

const FOOTER_COLUMNS: ReadonlyArray<{ title: TranslationKey; links: ReadonlyArray<{ href: string; label: TranslationKey }> }> = [
  {
    title: "footer.explore",
    links: [
      { href: "/public/alerts", label: "nav.alerts" },
      { href: "/public/map", label: "nav.map" },
      { href: "/public/routes", label: "nav.routes" },
      { href: "/public/operators", label: "nav.operators" },
    ],
  },
  {
    title: "footer.byPhone",
    links: [
      { href: "/public/subscribe", label: "footer.getPhoneAlerts" },
      { href: "/public/subscription/manage", label: "footer.manage" },
      { href: "/public/subscription/manage", label: "footer.unsubscribe" },
    ],
  },
  {
    title: "footer.about",
    links: [
      { href: "/public#about", label: "footer.aboutLink" },
      { href: "/public#how", label: "footer.howReviewed" },
    ],
  },
];

export async function SiteFooter() {
  const { t, rich } = await getI18n();
  return (
    <footer className="mt-16 bg-slate-900 py-12 text-sm text-slate-300 print:hidden">
      <Container>
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="space-y-3 sm:col-span-2 lg:col-span-1">
            <div className="flex items-center gap-2">
              <BrandMark className="size-9" />
              <Wordmark tone="light" className="text-lg" />
            </div>
            <p className="max-w-xs leading-relaxed">{t("footer.tagline")}</p>
            <LanguageSwitcher tone="dark" />
          </div>
          {FOOTER_COLUMNS.map((col) => (
            <nav key={col.title} aria-label={t(col.title)}>
              <h2 className="mb-2 text-sm font-semibold text-emerald-300">{t(col.title)}</h2>
              <ul>
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="inline-flex min-h-10 items-center text-slate-100 hover:text-white hover:underline">
                      {t(l.label)}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <p className="mt-10 max-w-4xl border-t border-slate-700 pt-6 leading-relaxed text-slate-300">
          {rich("footer.disclaimer", { b: (c) => <strong className="font-semibold text-white">{c}</strong> })}
        </p>
      </Container>
    </footer>
  );
}
