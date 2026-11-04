import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Lock, ShieldCheck, UserRound } from "lucide-react";
import { PageShell } from "@/components/public/site-chrome";
import { SubscribeForm } from "@/components/public/subscribe-form";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";
import type { TranslationKey } from "@/lib/i18n/translate";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.subscribe.title") };
}

const POINTS: ReadonlyArray<{ icon: typeof Lock; title: TranslationKey; text: TranslationKey }> = [
  { icon: ShieldCheck, title: "subscribe.point.verifiedTitle", text: "subscribe.point.verified" },
  { icon: ShieldCheck, title: "subscribe.point.reviewedTitle", text: "subscribe.point.reviewed" },
  { icon: Lock, title: "subscribe.point.privateTitle", text: "subscribe.point.private" },
];

async function SubscribeContent() {
  const { t } = await getI18n();
  return (
    <PageShell title={t("subscribe.title")} intro={t("subscribe.intro")}>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_36rem] lg:gap-12">
        <SubscribeForm />
        <aside aria-label={t("alerts.aboutAside")} className="space-y-6 lg:order-first lg:pt-2">
          <ul className="space-y-5">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3.5">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
                  <Icon className="size-5" />
                </span>
                <div>
                  <h2 className="font-bold text-slate-900">{t(title)}</h2>
                  <p className="mt-0.5 text-sm leading-relaxed text-slate-600">{t(text)}</p>
                </div>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700" aria-hidden>
              <UserRound className="size-5" />
            </span>
            <p>
              <strong className="text-slate-900">{t("subscribe.already")}</strong>
              <br />
              <Link href="/public/subscription/manage" className="font-semibold text-emerald-800 underline underline-offset-2">
                {t("subscribe.manageLink")}
              </Link>
            </p>
          </div>
        </aside>
      </div>
    </PageShell>
  );
}

export default function SubscribePage() {
  return (
    <Suspense fallback={<PageFallback />}>
      <SubscribeContent />
    </Suspense>
  );
}
