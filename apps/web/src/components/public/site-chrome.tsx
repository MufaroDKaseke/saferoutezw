import { Info, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export { ErrorNotice } from "@/components/public/error-notice";
export { SiteHeader } from "@/components/public/site-header";

/** Page width and gutters shared by every public section. */
export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
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
