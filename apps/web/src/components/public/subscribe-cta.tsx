import Link from "next/link";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

const POINTS = ["By SMS or WhatsApp", "Choose provinces or road corridors", "Your number is verified first", "Unsubscribe any time"];

/** Full-width promotion for phone alerts. */
export function SubscribeBand() {
  return (
    <section aria-labelledby="sub-cta" className="grid items-center gap-8 rounded-3xl bg-slate-900 p-6 text-white sm:p-10 lg:grid-cols-[1.2fr_1fr] lg:gap-12">
      <div className="space-y-5">
        <h2 id="sub-cta" className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          Road updates that reach you.
        </h2>
        <p className="max-w-lg text-base leading-relaxed text-slate-300 sm:text-lg">
          Get reviewed road notices for the areas you travel, straight to your phone. No app and no account.
        </p>
        <ul className="grid gap-2 text-[15px] text-slate-100 sm:grid-cols-2">
          {POINTS.map((p) => (
            <li key={p} className="flex items-center gap-2">
              <Check className="size-4 shrink-0 text-emerald-400" aria-hidden /> {p}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3 pt-1">
          <Button asChild size="lg" className="h-12 bg-emerald-500 px-5 text-base text-emerald-950 hover:bg-emerald-400">
            <Link href="/public/subscribe">
              <Bell /> Get alerts
            </Link>
          </Button>
          <Button asChild size="lg" variant="ghost" className="h-12 px-5 text-base text-white hover:bg-white/10 hover:text-white">
            <Link href="/public/subscription/manage">Manage subscription</Link>
          </Button>
        </div>
      </div>
      <figure className="mx-auto w-full max-w-sm space-y-2">
        <div className="space-y-3 rounded-2xl bg-white p-4 text-slate-900 shadow-xl shadow-black/30">
          <p className="text-sm font-bold">SafeRouteZW</p>
          <p className="rounded-xl rounded-bl-sm bg-slate-100 p-3 text-[15px] leading-relaxed">
            Road notice: a published alert for your area. Open the link for details and check again before you travel.
          </p>
        </div>
        <figcaption className="text-center text-xs text-slate-400">Example of the style of message. Not a real alert.</figcaption>
      </figure>
    </section>
  );
}

/** Compact version for sidebars. */
export function SubscribeCard() {
  return (
    <section aria-labelledby="sub-card" className="space-y-3 rounded-2xl bg-slate-900 p-5 text-white">
      <span className="flex size-11 items-center justify-center rounded-xl bg-emerald-500 text-emerald-950" aria-hidden>
        <Bell className="size-5" />
      </span>
      <h2 id="sub-card" className="text-lg font-bold tracking-tight">
        Road updates that reach you.
      </h2>
      <p className="text-sm leading-relaxed text-slate-300">New notices for your province or corridor, by SMS or WhatsApp.</p>
      <Button asChild size="lg" className="w-full bg-emerald-500 text-emerald-950 hover:bg-emerald-400">
        <Link href="/public/subscribe">Get alerts</Link>
      </Button>
    </section>
  );
}
