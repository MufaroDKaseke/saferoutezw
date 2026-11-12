"use client";

import Link from "next/link";
import { useState } from "react";
import { CalendarClock, Clock, Newspaper, NotebookPen, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, QueryError, CardBodySkeleton } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { listStories } from "@/lib/api/newsroom";
import { formatShort } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import { canApprove } from "@/lib/newsroom/roles";
import { BOARD_STAGES, STORY_STAGE_LABEL, type StoryStage } from "@/lib/newsroom/taxonomy";
import type { StorySummary } from "@/lib/newsroom/types";
import { StoryStageBadge, VerifiedBadge } from "./story-badges";

type View = "board" | "queue";

/** Past its deadline and still not approved or on air. */
export function isOverdue(story: Pick<StorySummary, "deadline_at" | "stage">, now: number = Date.now()): boolean {
  if (!story.deadline_at) return false;
  if (story.stage === "approved" || story.stage === "broadcast" || story.stage === "dropped") return false;
  return new Date(story.deadline_at).getTime() < now;
}

function StoryCard({ story }: { story: StorySummary }) {
  const overdue = isOverdue(story);
  return (
    <li className="rounded-lg border bg-card p-3 shadow-xs">
      <Link href={`/stories/${story.id}`} className="block text-sm leading-snug font-semibold text-foreground hover:underline">
        {story.title}
      </Link>
      <dl className="mt-2 space-y-1 text-xs text-slate-700">
        <div className="flex items-center gap-1.5">
          <User className="size-3.5 shrink-0 text-slate-500" aria-hidden />
          <dt className="sr-only">Reporter</dt>
          <dd>{story.assignee.display_name}</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <CalendarClock className="size-3.5 shrink-0 text-slate-500" aria-hidden />
          <dt className="sr-only">Deadline</dt>
          <dd className={overdue ? "font-semibold text-red-800" : undefined}>
            {story.deadline_at ? formatShort(story.deadline_at) : "No deadline"}
            {overdue ? " · Overdue" : ""}
          </dd>
        </div>
        {story.latest_script_seconds !== null ? (
          <div className="flex items-center gap-1.5">
            <Clock className="size-3.5 shrink-0 text-slate-500" aria-hidden />
            <dt className="sr-only">Reading time</dt>
            <dd className="tnum">
              {formatClock(story.latest_script_seconds)} · v{story.latest_script_version}
            </dd>
          </div>
        ) : null}
      </dl>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <VerifiedBadge verified={story.verified} />
        {story.approved_script_version !== null && story.stage !== "approved" ? (
          <Chip tone="emerald">v{story.approved_script_version} approved</Chip>
        ) : null}
      </div>
    </li>
  );
}

function Column({ stage, stories }: { stage: StoryStage; stories: StorySummary[] }) {
  const headingId = `column-${stage}`;
  return (
    <section aria-labelledby={headingId} className="min-w-0 rounded-xl bg-slate-50 p-3">
      <h2 id={headingId} className="mb-3 flex items-center justify-between gap-2 text-sm font-bold text-foreground">
        {STORY_STAGE_LABEL[stage]}
        <span className="tnum rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-slate-700">{stories.length}</span>
      </h2>
      {stories.length === 0 ? (
        <p className="py-4 text-center text-xs text-slate-500">Nothing here</p>
      ) : (
        <ul className="space-y-2">
          {stories.map((s) => (
            <StoryCard key={s.id} story={s} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** The Executive Producer's approval queue: submitted scripts, longest-waiting first. */
function ApprovalQueue({ stories }: { stories: StorySummary[] }) {
  if (stories.length === 0) {
    return <EmptyState title="Nothing is waiting for approval" description="Submitted scripts show up here." />;
  }
  return (
    <ul className="divide-y rounded-xl border bg-card" aria-label="Awaiting approval">
      {stories.map((s) => (
        <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold">{s.title}</p>
            <p className="mt-0.5 text-xs text-slate-600">
              {s.assignee.display_name} · submitted {formatShort(s.updated_at)}
              {s.latest_script_seconds !== null ? ` · ${formatClock(s.latest_script_seconds)} to read` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StoryStageBadge stage={s.stage} />
            <Button asChild size="sm">
              <Link href={`/stories/${s.id}`}>Review</Link>
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function StoryBoard() {
  const { user } = useSession();
  const approver = canApprove(user?.role);
  const [view, setView] = useState<View>("board");
  const stories = useResource("newsroom:stories:board", () => listStories({ stage: BOARD_STAGES, pageSize: 100 }));

  if (stories.error) return <QueryError error={stories.error} onRetry={stories.refetch} what="stories" />;
  const items = stories.data?.items;

  const awaiting = (items ?? []).filter((s) => s.stage === "in_review").sort((a, b) => a.updated_at.localeCompare(b.updated_at));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Stories"
        description={
          approver
            ? "Every story in the newsroom, from taking an article to approval. Approve scripts or send them back."
            : "Your stories, from taking an article to approval."
        }
        actions={
          <Button asChild variant="outline">
            <Link href="/news">
              <Newspaper aria-hidden /> Find an article
            </Link>
          </Button>
        }
      />

      {approver ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="View">
          <Button variant={view === "board" ? "default" : "outline"} aria-pressed={view === "board"} onClick={() => setView("board")}>
            Board
          </Button>
          <Button variant={view === "queue" ? "default" : "outline"} aria-pressed={view === "queue"} onClick={() => setView("queue")}>
            Awaiting approval ({awaiting.length})
          </Button>
        </div>
      ) : null}

      {!items ? (
        <CardBodySkeleton lines={8} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={NotebookPen}
          title={approver ? "No stories yet" : "You have no stories yet"}
          description="Open an article in the News Monitor and choose “Take this story” to start one."
          action={
            <Button asChild>
              <Link href="/news">Go to the News Monitor</Link>
            </Button>
          }
        />
      ) : approver && view === "queue" ? (
        <ApprovalQueue stories={awaiting} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {BOARD_STAGES.map((stage) => (
            <Column key={stage} stage={stage} stories={items.filter((s) => s.stage === stage)} />
          ))}
        </div>
      )}
    </div>
  );
}
