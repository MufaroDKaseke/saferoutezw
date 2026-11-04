import Link from "next/link";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getI18n } from "@/lib/i18n/server";
import type { TranslationKey } from "@/lib/i18n/translate";

const POINTS: TranslationKey[] = ["promo.point.channels", "promo.point.areas", "promo.point.verified", "promo.point.unsubscribe"];

/** Full-width promotion for phone alerts. */
export async function SubscribeBand() {
  const { t } = await getI18n();
  return (
    <section aria-labelledby="sub-cta" className="grid items-center gap-8 rounded-3xl bg-slate-900 p-6 text-white sm:p-10 lg:grid-cols-[1.2fr_1fr] lg:gap-12">
      <div className="space-y-5">
        <h2 id="sub-cta" className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          {t("promo.title")}
        </h2>
        <p className="max-w-lg text-base leading-relaxed text-slate-300 sm:text-lg">{t("promo.body")}</p>
        <ul className="grid gap-2 text-[15px] text-slate-100 sm:grid-cols-2">
          {POINTS.map((p) => (
            <li key={p} className="flex items-center gap-2">
              <Check className="size-4 shrink-0 text-emerald-400" aria-hidden /> {t(p)}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3 pt-1">
          <Button asChild size="lg" className="h-12 bg-emerald-500 px-5 text-base text-emerald-950 hover:bg-emerald-400">
            <Link href="/public/subscribe">
              <Bell /> {t("common.getAlerts")}
            </Link>
          </Button>
          <Button asChild size="lg" variant="ghost" className="h-12 px-5 text-base text-white hover:bg-white/10 hover:text-white">
            <Link href="/public/subscription/manage">{t("common.manageSubscription")}</Link>
          </Button>
        </div>
      </div>
      <figure className="mx-auto w-full max-w-sm space-y-2">
        <div className="space-y-3 rounded-2xl bg-white p-4 text-slate-900 shadow-xl shadow-black/30">
          <p className="text-sm font-bold">SafeRouteZW</p>
          <p className="rounded-xl rounded-bl-sm bg-slate-100 p-3 text-[15px] leading-relaxed">{t("promo.exampleMessage")}</p>
        </div>
        <figcaption className="text-center text-xs text-slate-400">{t("promo.exampleCaption")}</figcaption>
      </figure>
    </section>
  );
}

/** Compact version for sidebars. */
export async function SubscribeCard() {
  const { t } = await getI18n();
  return (
    <section aria-labelledby="sub-card" className="space-y-3 rounded-2xl bg-slate-900 p-5 text-white">
      <span className="flex size-11 items-center justify-center rounded-xl bg-emerald-500 text-emerald-950" aria-hidden>
        <Bell className="size-5" />
      </span>
      <h2 id="sub-card" className="text-lg font-bold tracking-tight">
        {t("promo.title")}
      </h2>
      <p className="text-sm leading-relaxed text-slate-300">{t("promo.cardBody")}</p>
      <Button asChild size="lg" className="w-full bg-emerald-500 text-emerald-950 hover:bg-emerald-400">
        <Link href="/public/subscribe">{t("common.getAlerts")}</Link>
      </Button>
    </section>
  );
}
