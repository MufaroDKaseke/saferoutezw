import Link from "next/link";
import { CircleAlert, Info, TriangleAlert } from "lucide-react";
import { BrandMark, Wordmark } from "@/components/layout/brand";
import { cn } from "@/lib/utils";

export { SiteHeader } from "@/components/public/site-header";

/** Page width and gutters shared by every public section. */
export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
}

const DISCLAIMER = (
  <>
    SafeRouteZW shares road safety notices that a human editor has reviewed and published. It may be incomplete or out of
    date. <strong className="font-semibold text-white">No alert on your route does not mean the road is safe.</strong>{" "}
    Follow police and traffic authority instructions.
  </>
);

const FOOTER_COLUMNS = [
  {
    title: "Explore",
    links: [
      { href: "/public/alerts", label: "Road Alerts" },
      { href: "/public/map", label: "Safety Map" },
      { href: "/public/routes", label: "Plan a Route" },
      { href: "/public/operators", label: "Transport Operators" },
    ],
  },
  {
    title: "Alerts by phone",
    links: [
      { href: "/public/subscribe", label: "Get SMS or WhatsApp alerts" },
      { href: "/public/subscription/manage", label: "Manage subscription" },
      { href: "/public/subscription/manage", label: "Unsubscribe" },
    ],
  },
  {
    title: "About",
    links: [
      { href: "/public#about", label: "About SafeRouteZW" },
      { href: "/public#how", label: "How notices are reviewed" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="mt-16 bg-slate-900 py-12 text-sm text-slate-300 print:hidden">
      <Container>
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="space-y-3 sm:col-span-2 lg:col-span-1">
            <div className="flex items-center gap-2">
              <BrandMark className="size-9" />
              <Wordmark tone="light" className="text-lg" />
            </div>
            <p className="max-w-xs leading-relaxed">
              Reviewed road safety notices and journey checks for Zimbabwe. Free to use, no account needed.
            </p>
          </div>
          {FOOTER_COLUMNS.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h2 className="mb-2 text-sm font-semibold text-emerald-300">{col.title}</h2>
              <ul>
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="inline-flex min-h-10 items-center text-slate-100 hover:text-white hover:underline">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <p className="mt-10 max-w-4xl border-t border-slate-700 pt-6 leading-relaxed text-slate-300">{DISCLAIMER}</p>
      </Container>
    </footer>
  );
}

export function PageShell({
  title,
  intro,
  children,
  aside,
}: {
  title: string;
  intro?: string;
  children: React.ReactNode;
  /** Optional right-hand content next to the heading (for example a status tag). */
  aside?: React.ReactNode;
}) {
  return (
    <Container className="space-y-6 py-8 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
          {intro ? <p className="max-w-2xl text-base leading-relaxed text-slate-600 sm:text-lg">{intro}</p> : null}
        </div>
        {aside}
      </div>
      {children}
    </Container>
  );
}

export function ErrorNotice({ message, title = "We could not load this information." }: { message: string; title?: string }) {
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold">{title}</p>
        <p>{message}</p>
      </div>
    </div>
  );
}

const NOTICE_TONES = {
  info: { box: "border-slate-200 bg-slate-100 text-slate-800", Icon: Info },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-900", Icon: TriangleAlert },
} as const;

/** Inline note with an icon. Use `warning` for safety caveats, `info` for helpful context. */
export function Notice({
  tone = "info",
  children,
  className,
  role,
}: {
  tone?: keyof typeof NOTICE_TONES;
  children: React.ReactNode;
  className?: string;
  role?: "note" | "status";
}) {
  const { box, Icon } = NOTICE_TONES[tone];
  return (
    <div role={role} className={cn("flex gap-2.5 rounded-xl border p-3 text-sm leading-relaxed", box, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/** Empty results: say why, then offer the next step. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  actions,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700" aria-hidden>
        <Icon className="size-7" />
      </span>
      <h3 className="text-lg font-bold text-slate-900">{title}</h3>
      {children ? <p className="max-w-md text-sm leading-relaxed text-slate-600">{children}</p> : null}
      {actions ? <div className="mt-1 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  );
}
