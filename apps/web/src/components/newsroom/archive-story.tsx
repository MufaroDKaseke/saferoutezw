"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ExternalLink, GitBranch } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, NotFoundState, QueryError } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { getArchivedStory, takeStory } from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import { canWriteStories } from "@/lib/newsroom/roles";
import type { ArchiveStoryDetail } from "@/lib/newsroom/types";
import { ScriptOriginBadge, SelfApprovedBadge } from "./story-badges";

function StoryHistory({ data }: { data: ArchiveStoryDetail }) {
  const { user } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const startFollowUp = async () => {
    setBusy(true);
    try {
      const created = await takeStory({ title: `Follow-up: ${data.title}`, followsStoryId: data.id });
      toast.success("Follow-up started");
      router.push(`/stories/${created.id}`);
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link href="/archive" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Archive
      </Link>

      <PageHeader
        meta={
          <>
            {data.category_label ? <Chip tone="indigo">{data.category_label}</Chip> : null}
            {data.follows ? (
              <Chip tone="slate" icon={GitBranch}>
                Follow-up
              </Chip>
            ) : null}
          </>
        }
        title={data.title}
        description={
          <>
            First aired {formatFull(data.aired_at)} · {data.reporter.display_name}
            {data.publisher ? ` · from ${data.publisher}` : ""}
          </>
        }
        actions={
          <>
            {data.source_item_id ? (
              <Button asChild variant="outline">
                <Link href={`/news/${data.source_item_id}`}>Source article</Link>
              </Button>
            ) : null}
            {data.source_url ? (
              <Button asChild variant="outline">
                <a href={data.source_url} target="_blank" rel="noopener noreferrer">
                  Original <ExternalLink aria-hidden />
                </a>
              </Button>
            ) : null}
            {canWriteStories(user?.role) ? (
              <Button disabled={busy} onClick={startFollowUp}>
                <GitBranch aria-hidden /> Start a follow-up
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          {data.scripts.map((s) => (
            <SectionCard
              key={s.version_number}
              title={`Aired script · version ${s.version_number}`}
              description={`${s.created_by.display_name} · ${formatFull(s.created_at)} · about ${formatClock(s.estimated_seconds)} to read`}
              action={<ScriptOriginBadge origin={s.origin} />}
            >
              <h3 className="text-sm font-semibold">{s.headline}</h3>
              <p className="mt-2 text-sm leading-relaxed whitespace-pre-line">{s.body}</p>
              <p className="mt-3 text-xs text-slate-600">
                Aired in{" "}
                {s.aired_in.map((b, i) => (
                  <span key={`${b.id}:${b.revision_number}`}>
                    {i > 0 ? ", " : ""}
                    {b.name} (revision {b.revision_number}, {formatFull(b.aired_at)})
                  </span>
                ))}
              </p>
            </SectionCard>
          ))}
        </div>

        <div className="space-y-6">
          <SectionCard title="Follow-ups" description="Stories that continue this one, once they have aired.">
            <div className="space-y-3 text-sm">
              {data.follows ? (
                <p>
                  This story follows{" "}
                  <Link href={`/archive/stories/${data.follows.id}`} className="font-semibold text-emerald-800 hover:underline">
                    {data.follows.title}
                  </Link>
                  .
                </p>
              ) : null}
              {data.followed_by.length > 0 ? (
                <ul className="space-y-1" aria-label="Follow-ups">
                  {data.followed_by.map((f) => (
                    <li key={f.id}>
                      <Link href={`/archive/stories/${f.id}`} className="font-semibold text-emerald-800 hover:underline">
                        {f.title}
                      </Link>{" "}
                      <span className="text-xs text-slate-600">aired {formatFull(f.aired_at)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-slate-600">No follow-ups have aired yet.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard title="Version history" description="Every version of the script. Only the versions that aired are shown in full.">
            <ol className="space-y-2 text-sm" aria-label="Script versions">
              {[...data.versions].reverse().map((v) => (
                <li key={v.version_number} className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">Version {v.version_number}</span>
                  <ScriptOriginBadge origin={v.origin} />
                  {v.approved ? <Chip tone="emerald">Approved</Chip> : <Chip tone="slate">Not approved</Chip>}
                  {v.aired ? <Chip tone="emerald">Aired</Chip> : null}
                  <span className="text-xs text-slate-600">
                    {v.created_by.display_name} · {formatFull(v.created_at)}
                  </span>
                </li>
              ))}
            </ol>
          </SectionCard>

          <SectionCard title="Decisions" description="Who approved or sent back the script.">
            {data.reviews.length === 0 ? (
              <p className="text-sm text-slate-600">No decisions were recorded.</p>
            ) : (
              <ul className="space-y-2 text-sm" aria-label="Decisions">
                {[...data.reviews].reverse().map((r, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
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
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

export function ArchiveStoryView({ id }: { id: string }) {
  const story = useResource(`newsroom:archive:story:${id}`, () => getArchivedStory(id));
  if (story.error) {
    if (story.error instanceof ApiError && story.error.status === 404) {
      return <NotFoundState what="archived story" action={<Link href="/archive">Back to the Archive</Link>} />;
    }
    return <QueryError error={story.error} onRetry={story.refetch} what="archived story" />;
  }
  if (!story.data) return <CardBodySkeleton lines={10} />;
  return <StoryHistory data={story.data} />;
}
