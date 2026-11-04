import type { Metadata } from "next";
import Link from "next/link";
import { Lock, ShieldCheck, UserRound } from "lucide-react";
import { PageShell } from "@/components/public/site-chrome";
import { SubscribeForm } from "@/components/public/subscribe-form";

export const metadata: Metadata = { title: "Get road alerts" };

const POINTS = [
  { icon: ShieldCheck, title: "Verified first", text: "We confirm your number with a one-time code before any alert is sent." },
  { icon: ShieldCheck, title: "Only reviewed notices", text: "Every alert was approved by a human editor." },
  { icon: Lock, title: "Your number stays private", text: "Used only for road alerts. Unsubscribe whenever you like." },
];

export default function SubscribePage() {
  return (
    <PageShell
      title="Get road alerts by SMS or WhatsApp"
      intro="No account needed. We verify your number first and only send alerts that editors have reviewed and published."
    >
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_36rem] lg:gap-12">
        <SubscribeForm />
        <aside aria-label="About these alerts" className="space-y-6 lg:order-first lg:pt-2">
          <ul className="space-y-5">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3.5">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700" aria-hidden>
                  <Icon className="size-5" />
                </span>
                <div>
                  <h2 className="font-bold text-slate-900">{title}</h2>
                  <p className="mt-0.5 text-sm leading-relaxed text-slate-600">{text}</p>
                </div>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700" aria-hidden>
              <UserRound className="size-5" />
            </span>
            <p>
              <strong className="text-slate-900">Already subscribed?</strong>
              <br />
              <Link href="/public/subscription/manage" className="font-semibold text-emerald-800 underline underline-offset-2">
                Manage or cancel your alerts
              </Link>
            </p>
          </div>
        </aside>
      </div>
    </PageShell>
  );
}
