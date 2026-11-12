"use client";

import Link from "next/link";
import { Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { CardBodySkeleton, EmptyState, QueryError } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useResource } from "@/hooks/use-resource";
import { listBulletins } from "@/lib/api/newsroom";
import { formatFull, formatShort } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import type { BulletinSummary } from "@/lib/newsroom/types";
import { AiredBadge } from "./bulletin-badges";

const LOOK_BACK_MS = 6 * 60 * 60 * 1000;

function Row({ b, next }: { b: BulletinSummary; next: boolean }) {
  const ready = b.approved_revision_number !== null;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-semibold">
          {b.name}
          {next ? <span className="ml-2 text-xs font-semibold text-indigo-800">Next up</span> : null}
        </p>
        <p className="mt-0.5 text-xs text-slate-600">
          {formatFull(b.scheduled_for)} · target {formatClock(b.target_seconds)}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {ready ? (
          <Chip tone="emerald">
            Version {b.approved_revision_number} approved{b.approved_at ? ` ${formatShort(b.approved_at)}` : ""}
          </Chip>
        ) : (
          <Chip tone="amber">Not approved yet</Chip>
        )}
        {b.aired_at ? <AiredBadge /> : null}
        <Button asChild size="sm">
          <Link href={`/studio/${b.id}`}>Open in studio</Link>
        </Button>
      </div>
    </li>
  );
}

/** Pick the bulletin to read: those from the last few hours and everything still to come, soonest first. */
export function StudioIndex() {
  const bulletins = useResource("newsroom:studio:index", () =>
    listBulletins({ order: "asc", scheduledFrom: new Date(Date.now() - LOOK_BACK_MS).toISOString(), pageSize: 50 }),
  );
  if (bulletins.error) return <QueryError error={bulletins.error} onRetry={bulletins.refetch} what="bulletins" />;
  const items = bulletins.data?.items;
  const nextId = items?.find((b) => !b.aired_at)?.id;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Studio"
        description="Pick a bulletin to read. The studio view shows only the approved version and checks the server every few seconds."
      />
      {!items ? (
        <CardBodySkeleton lines={5} />
      ) : items.length === 0 ? (
        <EmptyState icon={Mic} title="No bulletins to read" description="Bulletins from the last six hours and any still to come appear here." />
      ) : (
        <ul className="divide-y rounded-xl border bg-card" aria-label="Bulletins to read">
          {items.map((b) => (
            <Row key={b.id} b={b} next={b.id === nextId} />
          ))}
        </ul>
      )}
    </div>
  );
}
