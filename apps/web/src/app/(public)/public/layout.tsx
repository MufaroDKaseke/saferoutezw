import type { Metadata } from "next";
import { Suspense } from "react";
import { SiteFooter } from "@/components/public/site-footer";
import { SiteHeader } from "@/components/public/site-header";
import { I18nProvider } from "@/lib/i18n/provider";
import { getI18n, getLocale } from "@/lib/i18n/server";
import { MESSAGES } from "@/lib/i18n/messages";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return {
    title: { default: t("meta.site.title"), template: "%s · SafeRouteZW" },
    description: t("meta.site.description"),
  };
}

/** Public layout: no newsroom sidebar, no login. Pages own their width so the home hero can run edge to edge. */
export default function PublicLayout({ children }: LayoutProps<"/public">) {
  // The visitor's language comes from a cookie, which is request-time data, so everything that depends on
  // it sits under this Suspense boundary (Cache Components).
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50" aria-hidden />}>
      <Localized>{children}</Localized>
    </Suspense>
  );
}

async function Localized({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const { t } = await getI18n();
  return (
    <I18nProvider locale={locale} messages={MESSAGES[locale]}>
      {/* lang marks the page text for screen readers and browser translation; the <html> tag is shared with the newsroom. */}
      <div lang={locale} className="min-h-screen bg-slate-50">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-white focus:p-2">
          {t("common.skipToContent")}
        </a>
        {/* The header reads the current path (usePathname), which must sit inside Suspense on dynamic routes. */}
        <Suspense fallback={<div className="h-16 border-b border-slate-200 bg-white" aria-hidden />}>
          <SiteHeader />
        </Suspense>
        <main id="main">{children}</main>
        <SiteFooter />
      </div>
    </I18nProvider>
  );
}
