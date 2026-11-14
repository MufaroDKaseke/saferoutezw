"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Plus, Radio } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, EmptyState, QueryError } from "@/components/shared/states";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { createBulletin, listBulletins } from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import { canApprove } from "@/lib/newsroom/roles";
import type { BulletinSummary } from "@/lib/newsroom/types";
import { AiredBadge, RevisionStateBadge } from "./bulletin-badges";

/** A `datetime-local` value (no zone) means the browser's own clock; the API wants an instant. */
export function localInputToIso(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function Row({ b }: { b: BulletinSummary }) {
  const live = b.approved_revision_number !== null;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <Link href={`/bulletins/${b.id}`} className="text-sm font-semibold hover:underline">
          {b.name}
        </Link>
        <p className="mt-0.5 text-xs text-slate-600">
          {formatFull(b.scheduled_for)} · target {formatClock(b.target_seconds)}
          {live && b.approved_total_seconds !== null ? ` · runs ${formatClock(b.approved_total_seconds)}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {live ? <span className="text-xs font-semibold text-emerald-800">Live: revision {b.approved_revision_number}</span> : null}
        {b.latest_revision_state === "draft" || b.latest_revision_state === "pending_approval" || b.latest_revision_state === "rejected" ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
            Revision {b.latest_revision_number} <RevisionStateBadge state={b.latest_revision_state} />
          </span>
        ) : live ? null : (
          <RevisionStateBadge state={b.latest_revision_state} />
        )}
        {b.aired_at ? <AiredBadge /> : null}
      </div>
    </li>
  );
}

function CreateForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [when, setWhen] = useState("");
  const [minutes, setMinutes] = useState("5");
  const [busy, setBusy] = useState(false);

  const iso = when ? localInputToIso(when) : null;
  const seconds = Math.round(Number(minutes) * 60);
  const valid = name.trim() !== "" && iso !== null && Number.isFinite(seconds) && seconds >= 10 && seconds <= 7200;

  const create = async () => {
    if (!valid || iso === null) return;
    setBusy(true);
    try {
      const created = await createBulletin({ name: name.trim(), scheduledFor: iso, targetSeconds: seconds });
      toast.success("Bulletin created");
      router.push(`/bulletins/${created.id}`);
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
    }
  };

  return (
    <SectionCard title="New bulletin" description="A bulletin is made when it is needed: a name, when it goes to air and how long it should run.">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-end">
        <label className="block space-y-1">
          <span className="section-label">Name</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} aria-label="Bulletin name" placeholder="6pm news" />
        </label>
        <label className="block space-y-1">
          <span className="section-label">Goes to air</span>
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="Air time" />
        </label>
        <label className="block space-y-1">
          <span className="section-label">Length (minutes)</span>
          <Input type="number" min={1} max={120} step="any" value={minutes} onChange={(e) => setMinutes(e.target.value)} aria-label="Target length in minutes" />
        </label>
        <Button disabled={!valid || busy} onClick={create}>
          <Plus aria-hidden /> Create
        </Button>
      </div>
    </SectionCard>
  );
}

export function BulletinList() {
  const { user } = useSession();
  const approver = canApprove(user?.role);
  const bulletins = useResource("newsroom:bulletins", () => listBulletins({ pageSize: 50 }));

  if (bulletins.error) return <QueryError error={bulletins.error} onRetry={bulletins.refetch} what="bulletins" />;
  const items = bulletins.data?.items;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bulletins"
        description={
          approver
            ? "Line up approved stories, time the running order against the target, and approve each revision."
            : "The running orders for upcoming bulletins. The Executive Producer builds and approves them."
        }
        actions={
          <Button asChild variant="outline">
            <Link href="/studio">
              <Radio aria-hidden /> Studio view
            </Link>
          </Button>
        }
      />

      {approver ? <CreateForm /> : null}

      {!items ? (
        <CardBodySkeleton lines={6} />
      ) : items.length === 0 ? (
        <EmptyState icon={Radio} title="No bulletins yet" description={approver ? "Create one above to start lining up stories." : "Nothing has been scheduled yet."} />
      ) : (
        <ul className="divide-y rounded-xl border bg-card" aria-label="Bulletins">
          {items.map((b) => (
            <Row key={b.id} b={b} />
          ))}
        </ul>
      )}
    </div>
  );
}
