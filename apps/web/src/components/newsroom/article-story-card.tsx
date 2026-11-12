"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { NotebookPen } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/shared/section-card";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { listAssignees, takeStory } from "@/lib/api/newsroom";
import { canApprove, canWriteStories } from "@/lib/newsroom/roles";
import type { StoryLink } from "@/lib/newsroom/types";
import { StoryStageBadge } from "./story-badges";

/**
 * On the article page: the story built from this article and where it has got to, or the button that starts one.
 * Reporters take stories for themselves; the Executive Producer can also pick who it goes to.
 */
export function ArticleStoryCard({ articleId, story, onChanged }: { articleId: string; story: StoryLink | null; onChanged: () => void }) {
  const { user } = useSession();
  const router = useRouter();
  const writer = canWriteStories(user?.role);
  const approver = canApprove(user?.role);
  const [assigneeId, setAssigneeId] = useState("");
  const [busy, setBusy] = useState(false);

  const showPicker = approver && !story;
  const people = useResource(showPicker ? "newsroom:assignees" : "newsroom:assignees:off", async () => (showPicker ? listAssignees() : []));

  const take = async () => {
    setBusy(true);
    try {
      const created = await takeStory({ sourceItemId: articleId, assigneeId: assigneeId || undefined });
      toast.success("Story created");
      router.push(`/stories/${created.id}`);
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
      onChanged(); // someone may have taken it a moment ago: show who
    }
  };

  const assigningToSomeoneElse = !!assigneeId && assigneeId !== user?.id;
  // Reporters can only open their own stories, so only link when the viewer can actually open it.
  const canOpen = !!story && (approver || story.assignee.id === user?.id || user?.role === "analyst");

  return (
    <SectionCard
      title="Story"
      icon={<NotebookPen className="size-4" aria-hidden />}
      description="Turn this article into a script for a bulletin. The Reviewed / Used / Dismissed flag below is separate: it only tracks the article."
    >
      {story ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StoryStageBadge stage={story.stage} />
            <span className="text-sm text-slate-700">with {story.assignee.display_name}</span>
          </div>
          {canOpen ? (
            <Link href={`/stories/${story.id}`} className="block text-sm font-semibold hover:underline">
              {story.title}
            </Link>
          ) : (
            <p className="text-sm font-semibold">{story.title}</p>
          )}
        </div>
      ) : writer ? (
        <div className="space-y-3">
          {showPicker ? (
            <label className="block space-y-1">
              <span className="section-label">Assign to</span>
              <select
                value={assigneeId}
                onChange={(e) => setAssigneeId(e.target.value)}
                aria-label="Assign to"
                className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option value="">Me</option>
                {(people.data ?? [])
                  .filter((p) => p.id !== user?.id)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
              </select>
            </label>
          ) : null}
          <Button disabled={busy} onClick={take}>
            {assigningToSomeoneElse ? "Assign this story" : "Take this story"}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-slate-600">Nobody has taken this article as a story yet.</p>
      )}
    </SectionCard>
  );
}
