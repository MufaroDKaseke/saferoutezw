"use client";

import Link from "next/link";
import { AlertTriangle, ArrowLeft, Check, Clock, Hourglass, Loader2, Radio } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { NotFoundState } from "@/components/shared/states";
import { cn } from "@/lib/utils";
import { useStudioStatus, type StudioState } from "@/hooks/use-studio-status";
import { formatFull, formatShort, formatTimeSeconds } from "@/lib/formatters/date";
import { timeVersusTarget } from "@/lib/newsroom/bulletin";
import { formatClock } from "@/lib/newsroom/reading-time";
import type { StudioView } from "@/lib/newsroom/types";

/**
 * The studio view: read-only, for whoever reads on air. It shows the approved version and nothing else, and its
 * status comes only from a successful check against the server record. If the checks stop succeeding it says so.
 * It never hides the script when it cannot confirm it (the reader may be mid-bulletin) but never pretends either.
 */

function Banner({ state }: { state: StudioState }) {
  const { status, view, lastConfirmedAt, failures } = state;
  const confirmed = lastConfirmedAt ? formatTimeSeconds(lastConfirmedAt) : null;

  if (status === "cannot_confirm") {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-xl bg-red-50 p-4 text-red-950 ring-1 ring-red-200">
        <AlertTriangle className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <p className="text-lg font-bold">Cannot confirm</p>
          <p className="text-sm leading-snug">
            This screen cannot reach the server to check that it is showing the current version
            {failures > 0 ? ` (${failures} checks failed in a row)` : ""}.
            {view && confirmed ? ` What is below was last confirmed at ${confirmed} and may be out of date.` : " Nothing has been confirmed yet."}{" "}
            Check the connection, or ask the Executive Producer which version to read. It keeps trying and will update by itself.
          </p>
        </div>
      </div>
    );
  }
  if (status === "loading") {
    return (
      <div role="status" className="flex items-center gap-3 rounded-xl bg-slate-100 p-4 text-slate-800">
        <Loader2 className="size-5 animate-spin" aria-hidden />
        <p className="text-sm font-semibold">Checking with the server…</p>
      </div>
    );
  }
  if (!view) return null;
  if (status === "not_approved") {
    return (
      <div role="status" className="flex items-start gap-3 rounded-xl bg-slate-100 p-4 text-slate-900">
        <Clock className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <p className="text-lg font-bold">No approved version yet</p>
          <p className="text-sm">
            Nothing can be read on air until the Executive Producer approves this bulletin.
            {view.newer_revision_pending ? ` Version ${view.newer_revision_number} is waiting for approval.` : ""}
            {confirmed ? ` Confirmed with the server at ${confirmed}.` : ""}
          </p>
        </div>
      </div>
    );
  }
  if (status === "newer_pending") {
    return (
      <div role="status" className="flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-amber-950 ring-1 ring-amber-200">
        <Hourglass className="mt-0.5 size-6 shrink-0" aria-hidden />
        <div>
          <p className="text-lg font-bold">Newer version awaiting approval</p>
          <p className="text-sm">
            You are reading version {view.version}, the approved one. Version {view.newer_revision_number} has not been approved yet. This
            screen will switch by itself as soon as it is.
            {confirmed ? ` Confirmed with the server at ${confirmed}.` : ""}
          </p>
        </div>
      </div>
    );
  }
  return (
    <div role="status" className="flex items-start gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-950 ring-1 ring-emerald-200">
      <Check className="mt-0.5 size-6 shrink-0" aria-hidden />
      <div>
        <p className="text-lg font-bold">Current · Version {view.version}</p>
        <p className="text-sm">
          Approved {view.approved_at ? formatShort(view.approved_at) : ""}
          {view.approved_by ? ` by ${view.approved_by.display_name}` : ""}. Confirmed with the server at {confirmed}.
        </p>
      </div>
    </div>
  );
}

function Script({ view, unconfirmed }: { view: StudioView; unconfirmed: boolean }) {
  const time = timeVersusTarget(view.total_seconds, view.target_seconds);
  return (
    <div className={cn("space-y-4", unconfirmed && "opacity-90")}>
      <ol className="space-y-4" aria-label="Running order">
        {view.items.map((item) => (
          <li key={item.position} className="rounded-xl border bg-card p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-xl font-bold">
                <span className="tnum mr-2 text-slate-500">{item.position}.</span>
                {item.headline}
              </h2>
              <p className="tnum text-sm font-semibold text-slate-700">
                {formatClock(item.duration_seconds)}
                {item.duration_overridden ? " · clip" : ""}
              </p>
            </div>
            {item.note ? (
              <p className="mt-2 rounded-lg bg-indigo-50 px-3 py-2 text-base font-semibold text-indigo-950">Note: {item.note}</p>
            ) : null}
            <p className="mt-3 text-xl leading-relaxed whitespace-pre-line text-foreground">{item.body}</p>
          </li>
        ))}
      </ol>
      <p className="tnum text-sm text-slate-700">
        Running time {formatClock(view.total_seconds)} of {formatClock(view.target_seconds)} · {time.label}
      </p>
    </div>
  );
}

export function StudioScreen({ id }: { id: string }) {
  const state = useStudioStatus(id);
  const { status, view } = state;

  if (status === "not_found") {
    return <NotFoundState what="bulletin" action={<Link href="/studio">Back to the Studio</Link>} />;
  }

  return (
    <div className="space-y-6">
      <Link href="/studio" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Studio
      </Link>

      <PageHeader
        title={view?.name ?? "Studio"}
        description={view ? <>Goes to air {formatFull(view.scheduled_for)} · target {formatClock(view.target_seconds)}</> : undefined}
        meta={view?.aired_at ? <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-800"><Radio className="size-3.5" aria-hidden /> Broadcast</span> : undefined}
      />

      <Banner state={state} />

      {view && view.status === "approved" ? (
        <Script view={view} unconfirmed={status === "cannot_confirm"} />
      ) : null}
    </div>
  );
}
