"use client";

import { AlertTriangle, FileQuestion, Inbox, PlugZap, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EndpointNotAvailableError, NotFoundError, errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

function StateShell({
  icon: Icon,
  title,
  children,
  action,
  tone = "slate",
  className,
}: {
  icon: LucideIcon;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "slate" | "red" | "indigo";
  className?: string;
}) {
  const iconTone =
    tone === "red" ? "bg-red-100 text-red-700" : tone === "indigo" ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      <span className={cn("flex size-11 items-center justify-center rounded-xl", iconTone)}>
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="max-w-md space-y-1.5">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        {children ? <div className="text-sm leading-relaxed text-slate-600">{children}</div> : null}
      </div>
      {action}
    </div>
  );
}

/** Nothing matches, or nothing exists yet. Say what to do next. */
export function EmptyState({
  title,
  description,
  action,
  icon = Inbox,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <StateShell icon={icon} title={title} action={action} className={className}>
      {description}
    </StateShell>
  );
}

/** A request failed. Say what happened and offer a retry. */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: Error;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <StateShell
      icon={AlertTriangle}
      tone="red"
      title="This could not be loaded"
      className={className}
      action={
        onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        ) : undefined
      }
    >
      <span role="alert">{errorMessage(error)}</span>
    </StateShell>
  );
}

/**
 * api mode, endpoint missing. We show this instead of inventing data, and tell
 * the reader exactly which endpoint is missing and how to see the demo data.
 */
export function NotAvailableState({ endpoint, className }: { endpoint: string; className?: string }) {
  return (
    <StateShell icon={PlugZap} tone="indigo" title="Not available yet" className={className}>
      <p>
        The SafeRouteZW API does not provide this data yet, so there is nothing real to show. No numbers have
        been made up.
      </p>
      <p className="mt-2 text-xs">
        Missing endpoint: <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px]">{endpoint}</code>
      </p>
      <p className="mt-2 text-xs">
        To browse the labelled demo dataset, set <code className="font-mono text-[11px]">NEXT_PUBLIC_DATA_MODE=mock</code>.
      </p>
    </StateShell>
  );
}

export function NotFoundState({ what = "record", action }: { what?: string; action?: React.ReactNode }) {
  return (
    <StateShell icon={FileQuestion} title={`We could not find that ${what}`} action={action}>
      It may have been removed, or the link may be wrong.
    </StateShell>
  );
}

/** Choose the right state for any thrown error. */
export function QueryError({ error, onRetry, what }: { error: Error; onRetry?: () => void; what?: string }) {
  if (error instanceof EndpointNotAvailableError) return <NotAvailableState endpoint={error.endpoint} />;
  if (error instanceof NotFoundError) return <NotFoundState what={what} />;
  return <ErrorState error={error} onRetry={onRetry} />;
}

/* ---------------------------------------------------------------- loading */

export function LoadingStatus({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="sr-only">
      {label}…
    </span>
  );
}

export function CardBodySkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="space-y-3 px-5 py-2" aria-busy="true">
      <LoadingStatus />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn("h-4", i % 3 === 2 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-px" aria-busy="true">
      <LoadingStatus label="Loading table" />
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex items-center gap-4 border-t border-border px-4 py-4">
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} className={cn("h-4 flex-1", c === 0 && "max-w-24", c === 1 && "flex-[2]")} />
          ))}
        </div>
      ))}
    </div>
  );
}
