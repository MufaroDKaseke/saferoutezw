"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDown, ArrowLeft, ArrowUp, Check, Plus, Radio, Send, Trash2, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, NotFoundState, QueryError } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { ApiError, errorMessage } from "@/lib/api/errors";
import {
  approveRevision,
  broadcastBulletin,
  createRevision,
  getBulletin,
  listStories,
  rejectRevision,
  saveBulletinItems,
  submitRevision,
} from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import {
  defaultRevision,
  moveRow,
  rowFromStory,
  rowSeconds,
  rowsFromRevision,
  timeVersusTarget,
  toDrafts,
  totalSeconds,
  type BuilderRow,
} from "@/lib/newsroom/bulletin";
import { formatClock } from "@/lib/newsroom/reading-time";
import { canApprove } from "@/lib/newsroom/roles";
import { STORY_STAGE_LABEL, type StoryStage } from "@/lib/newsroom/taxonomy";
import type { BulletinDetail, BulletinRevision } from "@/lib/newsroom/types";
import { AiredBadge, RevisionStateBadge } from "./bulletin-badges";
import { SelfApprovedBadge } from "./story-badges";

export function BulletinBuilder({ id }: { id: string }) {
  const bulletin = useResource(`newsroom:bulletin:${id}`, () => getBulletin(id));
  if (bulletin.error) {
    if (bulletin.error instanceof ApiError && bulletin.error.status === 404) {
      return <NotFoundState what="bulletin" action={<Link href="/bulletins">Back to Bulletins</Link>} />;
    }
    return <QueryError error={bulletin.error} onRetry={bulletin.refetch} what="bulletin" />;
  }
  if (!bulletin.data) return <CardBodySkeleton lines={10} />;
  // Rebuild the editor whenever the saved record changes, so on-screen rows can never drift from it.
  const signature = JSON.stringify(
    bulletin.data.revisions.map((r) => [r.revision_number, r.state, r.aired_at, r.items.map((i) => [i.story.id, i.script.id, i.duration_seconds, i.note])]),
  );
  return <Builder key={`${bulletin.data.id}:${signature}`} data={bulletin.data} reload={bulletin.refetch} />;
}

/** Running time against the target, in words and numbers as well as a bar, so colour never carries it alone. */
function TimeBar({ total, target }: { total: number; target: number }) {
  const status = timeVersusTarget(total, target);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="tnum text-2xl font-bold">
          {formatClock(total)} <span className="text-sm font-medium text-slate-600">of {formatClock(target)}</span>
        </p>
        <p className={status.state === "over" ? "text-sm font-semibold text-red-800" : "text-sm font-semibold text-slate-700"}>{status.label}</p>
      </div>
      <div
        role="meter"
        aria-label="Running time against the target"
        aria-valuemin={0}
        aria-valuemax={target}
        aria-valuenow={Math.min(total, target)}
        aria-valuetext={`${formatClock(total)} of ${formatClock(target)}. ${status.label}`}
        className="h-2.5 overflow-hidden rounded-full bg-slate-100"
      >
        <div className={status.state === "over" ? "h-full bg-red-600" : "h-full bg-emerald-600"} style={{ width: `${status.percent}%` }} />
      </div>
    </div>
  );
}

function Builder({ data, reload }: { data: BulletinDetail; reload: () => void }) {
  const { user } = useSession();
  const approver = canApprove(user?.role);

  const working = data.revisions.find((r) => r.state === "draft" || r.state === "pending_approval");
  const live = data.revisions.find((r) => r.revision_number === data.approved_revision_number);
  const [selected, setSelected] = useState(defaultRevision(data.revisions, data.approved_revision_number).revision_number);
  const rev = data.revisions.find((r) => r.revision_number === selected) as BulletinRevision;
  const [rows, setRows] = useState<BuilderRow[]>(() => rowsFromRevision(rev));
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const editable = approver && rev.state === "draft";
  const dirty = JSON.stringify(toDrafts(rows)) !== JSON.stringify(toDrafts(rowsFromRevision(rev)));
  const total = editable ? totalSeconds(rows) : rev.total_seconds;
  const unapproved = rows.filter((r) => !r.approved);

  // Stories that can be lined up: approved ones, and ones still waiting for the Executive Producer.
  const candidates = useResource(editable ? "newsroom:stories:lineup" : "newsroom:stories:lineup:off", async () =>
    editable ? listStories({ stage: ["approved", "in_review"], pageSize: 100 }) : null,
  );
  const inBulletin = new Set(rows.map((r) => r.storyId));
  const available = (candidates.data?.items ?? []).filter((s) => !inBulletin.has(s.id) && s.latest_script_version !== null);

  const choose = (n: number) => {
    const next = data.revisions.find((r) => r.revision_number === n) as BulletinRevision;
    setSelected(n);
    setRows(rowsFromRevision(next));
  };

  const act = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await work();
      toast.success(done);
      setComment("");
      reload();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const update = (index: number, change: Partial<BuilderRow>) => setRows(rows.map((r, i) => (i === index ? { ...r, ...change } : r)));

  // The server refuses a bulletin with an unapproved script anyway; not offering the button saves a doomed request.
  const canSubmit = editable && !dirty && rows.length > 0 && unapproved.length === 0;
  const submitHint = !editable
    ? null
    : dirty
      ? "Save the running order before submitting."
      : rows.length === 0
        ? "Add at least one story."
        : unapproved.length > 0
          ? `${unapproved.length === 1 ? "One story has" : `${unapproved.length} stories have`} a script that is not approved yet. It cannot be submitted until ${unapproved.length === 1 ? "it is" : "they are"} approved.`
          : null;

  return (
    <div className="space-y-6">
      <Link href="/bulletins" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Bulletins
      </Link>

      <PageHeader
        meta={
          <>
            {live ? <Chip tone="emerald" icon={Check}>Live: revision {live.revision_number}</Chip> : <Chip tone="amber">Not approved yet</Chip>}
            {live?.aired_at ? <AiredBadge /> : null}
          </>
        }
        title={data.name}
        description={
          <>
            Goes to air {formatFull(data.scheduled_for)} · target {formatClock(data.target_seconds)}
          </>
        }
        actions={
          approver && live && !live.aired_at ? (
            <Button disabled={busy} variant="outline" onClick={() => act(() => broadcastBulletin(data.id), "Marked as broadcast")}>
              <Radio aria-hidden /> Mark as broadcast
            </Button>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Revisions">
            {[...data.revisions].reverse().map((r) => (
              <Button
                key={r.revision_number}
                size="sm"
                variant={r.revision_number === selected ? "default" : "outline"}
                aria-pressed={r.revision_number === selected}
                onClick={() => choose(r.revision_number)}
              >
                Revision {r.revision_number}
                {r.revision_number === data.approved_revision_number ? " · live" : ""}
              </Button>
            ))}
            {approver && !working ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => createRevision(data.id), "New revision started")}>
                <Plus aria-hidden /> Change this bulletin
              </Button>
            ) : null}
          </div>

          <SectionCard
            title={`Running order · revision ${rev.revision_number}`}
            description={
              editable
                ? "Reorder, time and annotate the stories. Each is pinned to one exact script version."
                : rev.state === "approved"
                  ? "This is what is approved and live. To change it, start a new revision: this one stays live until the new one is approved."
                  : "This revision can no longer be edited."
            }
            action={<RevisionStateBadge state={rev.state} />}
          >
            {rows.length === 0 ? (
              <p className="py-4 text-sm text-slate-600">{editable ? "No stories yet. Add approved stories from the list." : "This revision has no stories."}</p>
            ) : (
              <ol className="divide-y" aria-label="Running order">
                {rows.map((row, index) => (
                  <li key={row.storyId} className="py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold">
                          <span className="tnum mr-2 text-slate-500">{index + 1}.</span>
                          <Link href={`/stories/${row.storyId}`} className="hover:underline">
                            {row.title}
                          </Link>
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                          {row.scriptVersion !== null ? <span className="text-slate-600">Script version {row.scriptVersion}</span> : null}
                          {row.saved ? (
                            row.approved ? (
                              <Chip tone="emerald" icon={Check}>Script approved</Chip>
                            ) : (
                              <Chip tone="amber">Script not approved</Chip>
                            )
                          ) : (
                            <Chip tone="slate">Not saved yet</Chip>
                          )}
                          {row.newerScriptVersion !== null ? (
                            <Chip tone="amber">Newer script (version {row.newerScriptVersion}) exists</Chip>
                          ) : null}
                          <span className="text-slate-500">{STORY_STAGE_LABEL[row.stage as StoryStage] ?? row.stage}</span>
                        </div>
                      </div>
                      <p className="tnum text-sm font-semibold" aria-label={`Duration ${formatClock(rowSeconds(row))}`}>
                        {formatClock(rowSeconds(row))}
                        {row.overrideSeconds !== null ? <span className="ml-1 text-xs font-medium text-slate-600">clip</span> : null}
                      </p>
                    </div>

                    {editable ? (
                      <div className="mt-2 flex flex-wrap items-end gap-2">
                        <label className="space-y-1">
                          <span className="block text-xs text-slate-600">Clip length (seconds)</span>
                          <Input
                            type="number"
                            min={1}
                            max={3600}
                            value={row.overrideSeconds ?? ""}
                            placeholder={String(row.seconds)}
                            aria-label={`Clip length in seconds for ${row.title}`}
                            className="w-28"
                            onChange={(e) => update(index, { overrideSeconds: e.target.value === "" ? null : Math.max(1, Math.round(Number(e.target.value))) })}
                          />
                        </label>
                        <label className="min-w-40 flex-1 space-y-1">
                          <span className="block text-xs text-slate-600">Note for the newsreader</span>
                          <Input
                            value={row.note}
                            maxLength={500}
                            aria-label={`Note for ${row.title}`}
                            placeholder="For example: play clip 3 after the intro"
                            onChange={(e) => update(index, { note: e.target.value })}
                          />
                        </label>
                        <div className="flex gap-1">
                          <Button size="icon-sm" variant="outline" aria-label={`Move ${row.title} up`} disabled={index === 0} onClick={() => setRows(moveRow(rows, index, -1))}>
                            <ArrowUp aria-hidden />
                          </Button>
                          <Button size="icon-sm" variant="outline" aria-label={`Move ${row.title} down`} disabled={index === rows.length - 1} onClick={() => setRows(moveRow(rows, index, 1))}>
                            <ArrowDown aria-hidden />
                          </Button>
                          {row.newerScriptVersion !== null ? (
                            <Button size="sm" variant="outline" onClick={() => update(index, { scriptId: null, newerScriptVersion: null })}>
                              Use current approved version
                            </Button>
                          ) : null}
                          <Button size="icon-sm" variant="outline" aria-label={`Remove ${row.title}`} onClick={() => setRows(rows.filter((_, i) => i !== index))}>
                            <Trash2 aria-hidden />
                          </Button>
                        </div>
                      </div>
                    ) : row.note ? (
                      <p className="mt-1 text-xs text-slate-700">Note: {row.note}</p>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}

            {editable ? (
              <div className="mt-4 space-y-2 border-t pt-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    disabled={busy || !dirty}
                    onClick={() => act(() => saveBulletinItems(data.id, rev.revision_number, toDrafts(rows)), "Running order saved")}
                  >
                    Save running order
                  </Button>
                  <Button variant="outline" disabled={busy || !canSubmit} onClick={() => act(() => submitRevision(data.id, rev.revision_number), "Submitted for approval")}>
                    <Send aria-hidden /> Submit for approval
                  </Button>
                </div>
                {submitHint ? <p className="text-xs text-slate-600">{submitHint}</p> : null}
              </div>
            ) : null}
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Running time" description="Estimated from each script at the newsroom's reading speed. A clip's length replaces its estimate.">
            <TimeBar total={total} target={data.target_seconds} />
          </SectionCard>

          {approver && rev.state === "pending_approval" ? (
            <SectionCard title="Approval" description={`Revision ${rev.revision_number} is waiting for you. Approving makes it the live bulletin and supersedes the current one.`}>
              <div className="space-y-3">
                {rev.submitted_by && user && rev.submitted_by.id === user.id ? (
                  <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">You submitted this revision. You may approve it, and it will be recorded as self-approved.</p>
                ) : null}
                <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (required when rejecting)" maxLength={2000} aria-label="Approval comment" />
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy} onClick={() => act(() => approveRevision(data.id, rev.revision_number, comment), "Approved and live")}>
                    <Check aria-hidden /> Approve
                  </Button>
                  <Button variant="outline" disabled={busy || comment.trim() === ""} onClick={() => act(() => rejectRevision(data.id, rev.revision_number, comment), "Revision rejected")}>
                    <Undo2 aria-hidden /> Reject
                  </Button>
                </div>
              </div>
            </SectionCard>
          ) : null}

          {editable ? (
            <SectionCard title="Add stories" description="Approved stories, and ones still waiting for approval. A story can only be submitted once its script is approved.">
              {candidates.error ? (
                <p className="text-sm text-slate-600">The story list could not be loaded. {errorMessage(candidates.error)}</p>
              ) : !candidates.data ? (
                <CardBodySkeleton lines={3} />
              ) : available.length === 0 ? (
                <p className="text-sm text-slate-600">No more stories to add.</p>
              ) : (
                <ul className="divide-y" aria-label="Stories to add">
                  {available.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-3 py-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{s.title}</p>
                        <p className="text-xs text-slate-600">
                          {STORY_STAGE_LABEL[s.stage]} · {s.latest_script_seconds !== null ? formatClock(s.latest_script_seconds) : "no script"}
                        </p>
                      </div>
                      <Button size="sm" variant="outline" aria-label={`Add ${s.title}`} onClick={() => setRows([...rows, rowFromStory(s)])}>
                        <Plus aria-hidden /> Add
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          ) : null}

          <SectionCard title="History" description="Every revision and decision is kept. Nothing is overwritten.">
            <ol className="space-y-3 text-sm" aria-label="Revision history">
              {[...data.revisions].reverse().map((r) => (
                <li key={r.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">Revision {r.revision_number}</span>
                    <RevisionStateBadge state={r.state} />
                    {r.aired_at ? <AiredBadge /> : null}
                    <span className="text-xs text-slate-600">
                      {r.items.length} {r.items.length === 1 ? "story" : "stories"} · {formatClock(r.total_seconds)}
                    </span>
                  </div>
                  <ul className="mt-1 space-y-1 text-xs text-slate-700">
                    {r.decisions.map((d, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-2">
                        <span>
                          {d.decision === "approved" ? "Approved" : "Rejected"} by {d.reviewer.display_name} · {formatFull(d.decided_at)}
                        </span>
                        {d.self_approved ? <SelfApprovedBadge /> : null}
                        {d.comment ? <span className="w-full">“{d.comment}”</span> : null}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
