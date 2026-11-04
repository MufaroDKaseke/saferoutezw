import { ExternalLink as ExternalLinkIcon, Info, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Amber note used wherever an action is only a demonstration. Nothing here may
 * imply that something real was published, sent or saved to the database.
 */
export function SimulationNote({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      role="note"
      className={cn(
        "flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm leading-relaxed text-amber-950",
        className,
      )}
    >
      <Info className="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/** Indigo note for AI context, such as "a blackspot match is background, not evidence". */
export function ContextNote({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      role="note"
      className={cn(
        "flex gap-2.5 rounded-lg bg-indigo-50 px-3.5 py-3 text-sm leading-relaxed text-indigo-950",
        className,
      )}
    >
      <Info className="mt-0.5 size-4 shrink-0 text-indigo-600" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function PrivacyNote({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("flex items-start gap-2 text-xs leading-relaxed text-slate-600", className)}>
      <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

/**
 * Link to the original publisher. Demo articles point at fictional `.example`
 * addresses that do not exist, so they are shown as text instead of a dead link.
 */
export function PublisherLink({
  href,
  children,
  synthetic,
  className,
}: {
  href: string | null;
  children: React.ReactNode;
  synthetic?: boolean;
  className?: string;
}) {
  if (!href) return <span className={cn("text-slate-600", className)}>No URL recorded</span>;
  if (synthetic) {
    return (
      <span className={cn("inline-flex flex-wrap items-center gap-x-1.5 text-slate-700", className)}>
        <span className="break-all">{children}</span>
        <span className="text-xs text-amber-800">(demo address, not a real page)</span>
      </span>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn("inline-flex items-center gap-1 font-medium text-emerald-800 underline-offset-2 hover:underline", className)}
    >
      <span className="break-all">{children}</span>
      <ExternalLinkIcon className="size-3.5 shrink-0" aria-hidden />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
