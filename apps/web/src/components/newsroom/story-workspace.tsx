"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, Check, ExternalLink, Lock, Send, Sparkles, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, EmptyState, NotFoundState, QueryError } from "@/components/shared/states";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { ApiError, errorMessage } from "@/lib/api/errors";
import {
  draftScript,
  dropStory,
  getNewsroomArticle,
  getStory,
  reviewStory,
  saveScript,
  submitStory,
  verifyStory,
} from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import { countWords, estimateSeconds, formatClock } from "@/lib/newsroom/reading-time";
import { canApprove, canWriteStories } from "@/lib/newsroom/roles";
import { DROPPABLE_STAGES, SCRIPT_EDITABLE_STAGES, STORY_STAGE_LABEL, type StoryDecision } from "@/lib/newsroom/taxonomy";
import type { StoryDetail } from "@/lib/newsroom/types";
import { ScriptOriginBadge, SelfApprovedBadge, StoryStageBadge, VerifiedBadge } from "./story-badges";

const VERIFIABLE = ["assigned", "drafting", "changes_requested"] as const;
const SUBMITTABLE = ["assigned", "drafting", "changes_requested"] as const;
const DEFAULT_TARGET_SECONDS = 45;

export function StoryWorkspace({ id }: { id: string }) {
  const story = useResource(`newsroom:story:${id}`, () => getStory(id));
  if (story.error) {
    if (story.error instanceof ApiError && story.error.status === 404) {
      return <NotFoundState what="story" action={<Link href="/stories">Back to Stories</Link>} />;
    }
    if (story.error instanceof ApiError && story.error.status === 403) {
      return (
        <EmptyState
          icon={Lock}
          title="This story belongs to another reporter"
          description="Reporters can open their own stories. The Executive Producer can open every story."
          action={
            <Button asChild variant="outline">
              <Link href="/stories">Back to Stories</Link>
            </Button>
          }
        />
      );
    }
    return <QueryError error={story.error} onRetry={story.refetch} what="story" />;
  }
  if (!story.data) return <CardBodySkeleton lines={10} />;
  // A new version or stage rebuilds the editor from the saved record, so on-screen text can never drift from it.
  return <Workspace key={`${story.data.id}:${story.data.latest_script_version}:${story.data.stage}`} data={story.data} reload={story.refetch} />;
}

function ArticlePanel({ data }: { data: StoryDetail }) {
  const articleId = data.article?.id ?? null;
  const article = useResource(`newsroom:article:${articleId ?? "none"}`, async () => (articleId ? getNewsroomArticle(articleId) : null));
  if (!data.article) {
    return (
      <SectionCard title="Source article" description="This is an original story, so there is no article to read from.">
        <p className="text-sm text-slate-600">Write the script from your own reporting.</p>
      </SectionCard>
    );
  }
  const a = article.data;
  return (
    <SectionCard
      title="Source article"
      description={`${data.article.publisher} · personal details are redacted before storage. This is all the AI is ever sent.`}
      action={
        data.article.source_url ? (
          <a
            href={data.article.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-slate-700 hover:underline"
          >
            Original <ExternalLink className="size-3.5" aria-hidden />
          </a>
        ) : null
      }
    >
      <h3 className="mb-2 text-sm font-semibold">{data.article.headline}</h3>
      {article.error ? (
        <p className="text-sm text-slate-600">The article text could not be loaded. {errorMessage(article.error)}</p>
      ) : !a ? (
        <CardBodySkeleton lines={6} />
      ) : a.article_text || a.excerpt ? (
        <div className="max-h-144 overflow-y-auto text-sm leading-relaxed whitespace-pre-line text-slate-800">
          {a.article_text ?? a.excerpt}
        </div>
      ) : (
        <p className="text-sm text-slate-600">No article text was stored. Open the original article.</p>
      )}
    </SectionCard>
  );
}

function Workspace({ data, reload }: { data: StoryDetail; reload: () => void }) {
  const { user } = useSession();
  const role = user?.role;
  const writer = canWriteStories(role);
  const approver = canApprove(role);
  // Reporters act on their own stories; the Executive Producer on all. The server enforces the same rule.
  const mayAct = writer && (approver || user?.id === data.assignee.id);

  const latest = data.scripts.length > 0 ? data.scripts[data.scripts.length - 1] : null;
  const [headline, setHeadline] = useState(latest?.headline ?? data.title);
  const [body, setBody] = useState(latest?.body ?? "");
  const [note, setNote] = useState(data.verification?.note ?? "");
  const [comment, setComment] = useState("");
  const [targetSeconds, setTargetSeconds] = useState(String(DEFAULT_TARGET_SECONDS));
  const [confirmDrop, setConfirmDrop] = useState(false);
  const [busy, setBusy] = useState(false);

  const editable = mayAct && SCRIPT_EDITABLE_STAGES.includes(data.stage);
  const canVerify = mayAct && (VERIFIABLE as readonly string[]).includes(data.stage);
  const dirty = latest ? headline !== latest.headline || body !== latest.body : body.trim() !== "";
  const canSave = editable && dirty && headline.trim() !== "" && body.trim() !== "";
  const canSubmit = mayAct && (SUBMITTABLE as readonly string[]).includes(data.stage) && data.verified && !!latest && !dirty;
  const canDraft = editable && data.verified && data.source_item_id !== null && !dirty;
  const canReview = approver && data.stage === "in_review" && !!latest;
  const canDrop = mayAct && DROPPABLE_STAGES.includes(data.stage);
  const sentBack = data.stage === "changes_requested" ? [...data.reviews].reverse().find((r) => r.decision === "changes_requested") : undefined;
  const reviewingOwnWork = !!latest && !!user && (user.id === data.assignee.id || user.id === latest.created_by.id);

  const seconds = estimateSeconds(body, data.reading_wpm);
  const words = countWords(body);

  const act = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await work();
      toast.success(done);
      reload();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const decide = (decision: StoryDecision) =>
    act(
      () => reviewStory(data.id, { decision, scriptVersion: latest!.version_number, comment }),
      decision === "approved" ? "Approved" : "Sent back to the reporter",
    );

  return (
    <div className="space-y-6">
      <Link href="/stories" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Stories
      </Link>

      <PageHeader
        meta={
          <>
            <StoryStageBadge stage={data.stage} />
            <VerifiedBadge verified={data.verified} />
          </>
        }
        title={data.title}
        description={
          <>
            {data.assignee.display_name} · {data.deadline_at ? `deadline ${formatFull(data.deadline_at)}` : "no deadline"}
          </>
        }
        actions={
          canDrop ? (
            confirmDrop ? (
              <>
                <span className="text-sm text-slate-700">Drop this story?</span>
                <Button variant="destructive" disabled={busy} onClick={() => act(() => dropStory(data.id), "Story dropped")}>
                  Yes, drop it
                </Button>
                <Button variant="outline" onClick={() => setConfirmDrop(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={() => setConfirmDrop(true)}>
                Drop story
              </Button>
            )
          ) : null
        }
      />

      {sentBack ? (
        <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <strong>Sent back by {sentBack.reviewer.display_name}:</strong> {sentBack.comment}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,4fr)]">
        <ArticlePanel data={data} />

        <div className="space-y-6">
          {canReview ? (
            <SectionCard
              title="Approval"
              description={`Version ${latest!.version_number} is waiting for you. Approving applies to exactly this text.`}
            >
              <div className="space-y-3">
                {reviewingOwnWork ? (
                  <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                    You wrote or are assigned this story. You may approve it, and it will be recorded as self-approved.
                  </p>
                ) : null}
                <Textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Comment (required when sending the story back)"
                  maxLength={2000}
                  aria-label="Review comment"
                />
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy} onClick={() => decide("approved")}>
                    <Check aria-hidden /> Approve
                  </Button>
                  <Button variant="outline" disabled={busy || comment.trim() === ""} onClick={() => decide("changes_requested")}>
                    <Undo2 aria-hidden /> Send back
                  </Button>
                </div>
              </div>
            </SectionCard>
          ) : null}

          <SectionCard
            title="Verification"
            description="How were the facts checked? Needed before the story can be submitted or an AI draft requested."
            action={<VerifiedBadge verified={data.verified} />}
          >
            {canVerify ? (
              <div className="space-y-3">
                <Textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="For example: phoned the council press office and checked the minutes."
                  maxLength={2000}
                  aria-label="Verification note"
                />
                <Button disabled={busy || note.trim() === ""} onClick={() => act(() => verifyStory(data.id, note), "Verification recorded")}>
                  {data.verified ? "Update verification" : "Record verification"}
                </Button>
              </div>
            ) : data.verification ? (
              <p className="text-sm leading-relaxed">{data.verification.note}</p>
            ) : (
              <p className="text-sm text-slate-600">No verification was recorded.</p>
            )}
            {data.verification ? (
              <p className="mt-3 text-xs text-slate-600">
                Recorded by {data.verification.by.display_name} on {formatFull(data.verification.at)}
              </p>
            ) : null}
          </SectionCard>

          <SectionCard
            title="Script"
            description={
              latest
                ? `Version ${latest.version_number} · ${latest.created_by.display_name} · ${formatFull(latest.created_at)}`
                : "Nothing written yet."
            }
            action={latest ? <ScriptOriginBadge origin={latest.origin} /> : null}
          >
            {editable ? (
              <div className="space-y-3">
                <label className="block space-y-1">
                  <span className="section-label">Headline</span>
                  <Input value={headline} onChange={(e) => setHeadline(e.target.value)} maxLength={200} aria-label="Headline" />
                </label>
                <label className="block space-y-1">
                  <span className="section-label">Script, as it will be read</span>
                  <Textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    rows={12}
                    maxLength={8000}
                    aria-label="Script"
                    className="leading-relaxed"
                  />
                </label>
                <p className="tnum text-sm text-slate-700" aria-live="polite">
                  {words} words · about {formatClock(seconds)} to read at {data.reading_wpm} words a minute
                </p>
                {latest?.origin === "ai_draft" && !dirty ? (
                  <p className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900">
                    This is an AI draft. Check every fact against the article and edit it before you submit it.
                  </p>
                ) : null}
                {data.stage === "approved" ? (
                  <p className="text-xs text-slate-600">
                    Editing an approved script saves a new version that needs approval again. Version {data.approved_script_version} stays
                    the approved one until then.
                  </p>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    disabled={busy || !canSave}
                    onClick={() => act(() => saveScript(data.id, { headline, body, baseVersion: latest?.version_number ?? null }), "Saved as a new version")}
                  >
                    Save new version
                  </Button>
                  <Button disabled={busy || !canSubmit} onClick={() => act(() => submitStory(data.id), "Submitted for approval")}>
                    <Send aria-hidden /> Submit for approval
                  </Button>
                </div>
                {!canSubmit ? (
                  <p className="text-xs text-slate-600">
                    {!data.verified
                      ? "Record how the story was verified before submitting."
                      : !latest
                        ? "Save a script before submitting."
                        : dirty
                          ? "Save your changes before submitting."
                          : null}
                  </p>
                ) : null}

                <div className="border-t pt-3">
                  <p className="section-label mb-2">AI first draft</p>
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="space-y-1">
                      <span className="block text-xs text-slate-600">Length (seconds)</span>
                      <Input
                        type="number"
                        min={10}
                        max={600}
                        value={targetSeconds}
                        onChange={(e) => setTargetSeconds(e.target.value)}
                        aria-label="Target length in seconds"
                        className="w-24"
                      />
                    </label>
                    <Button
                      variant="outline"
                      disabled={busy || !canDraft}
                      onClick={() =>
                        act(
                          () =>
                            draftScript(data.id, {
                              baseVersion: latest?.version_number ?? null,
                              targetSeconds: Math.min(600, Math.max(10, Number(targetSeconds) || DEFAULT_TARGET_SECONDS)),
                            }),
                          "AI draft saved. Check it and edit it.",
                        )
                      }
                    >
                      <Sparkles aria-hidden /> Draft with AI
                    </Button>
                  </div>
                  <p className="mt-2 text-xs text-slate-600">
                    {!data.verified
                      ? "Available after you record verification."
                      : data.source_item_id === null
                        ? "Available for stories built from an article."
                        : dirty
                          ? "Save or undo your changes first: a draft becomes the next version."
                          : "Only the redacted article is sent to the AI. The draft is a starting point, never an approval."}
                  </p>
                </div>
              </div>
            ) : latest ? (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold">{latest.headline}</h3>
                <p className="text-sm leading-relaxed whitespace-pre-line">{latest.body}</p>
                <p className="tnum text-xs text-slate-600">
                  About {formatClock(latest.estimated_seconds)} to read at {data.reading_wpm} words a minute
                </p>
              </div>
            ) : (
              <p className="text-sm text-slate-600">No script has been written.</p>
            )}
          </SectionCard>

          {data.scripts.length > 0 || data.reviews.length > 0 ? (
            <SectionCard title="History" description="Every version and decision is kept. Nothing is overwritten.">
              <ol className="space-y-3 text-sm" aria-label="Script versions">
                {[...data.scripts].reverse().map((s) => (
                  <li key={s.id}>
                    <details>
                      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
                        <span className="font-semibold">Version {s.version_number}</span>
                        <ScriptOriginBadge origin={s.origin} />
                        {data.approved_script_version === s.version_number ? <span className="text-xs font-semibold text-emerald-800">Approved</span> : null}
                        <span className="text-xs text-slate-600">
                          {s.created_by.display_name} · {formatFull(s.created_at)} · {formatClock(s.estimated_seconds)}
                        </span>
                      </summary>
                      <div className="mt-2 rounded-lg bg-slate-50 p-3">
                        <p className="font-semibold">{s.headline}</p>
                        <p className="mt-1 leading-relaxed whitespace-pre-line">{s.body}</p>
                      </div>
                    </details>
                  </li>
                ))}
              </ol>
              {data.reviews.length > 0 ? (
                <ul className="mt-4 space-y-2 border-t pt-3 text-sm" aria-label="Decisions">
                  {[...data.reviews].reverse().map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">
                        {r.decision === "approved" ? "Approved" : "Sent back"} version {r.script_version}
                      </span>
                      {r.self_approved ? <SelfApprovedBadge /> : null}
                      <span className="text-xs text-slate-600">
                        {r.reviewer.display_name} · {formatFull(r.reviewed_at)}
                      </span>
                      {r.comment ? <span className="w-full text-slate-700">“{r.comment}”</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </SectionCard>
          ) : null}

          <p className="text-xs text-slate-600">
            Stage: {STORY_STAGE_LABEL[data.stage]}
            {data.approved_script_version !== null ? ` · approved version ${data.approved_script_version}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
