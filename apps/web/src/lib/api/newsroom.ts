import type {
  ArchiveBulletin,
  ArchiveBulletinDetail,
  ArchivePage,
  ArchiveQuery,
  ArchiveStory,
  ArchiveStoryDetail,
  Assignee,
  BulletinDetail,
  BulletinItemDraft,
  BulletinPage,
  NewsroomArticleDetail,
  NewsroomPage,
  NewsroomQuery,
  NewsroomSummary,
  StoryDetail,
  StoryPage,
  StoryQuery,
  StudioView,
  TakeStoryInput,
} from "@/lib/newsroom/types";
import type { ReviewStatus, StoryDecision } from "@/lib/newsroom/taxonomy";
import { apiRequest } from "./client";

/** NUST FM newsroom API. It only exists when the backend runs with APP_MODE=nust_newsroom. */

export function listNewsroomArticles(q: NewsroomQuery, signal?: AbortSignal): Promise<NewsroomPage> {
  return apiRequest<NewsroomPage>("GET /api/v1/newsroom/articles", {
    signal,
    query: {
      page: q.page,
      page_size: q.pageSize,
      q: q.q,
      publisher_id: q.publisherId,
      category: q.category,
      state: q.state,
      review_status: q.reviewStatus,
      published_from: q.publishedFrom,
      collected_from: q.collectedFrom,
      sort: q.sort,
      order: q.order,
    },
  });
}

export function getNewsroomArticle(id: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("GET /api/v1/newsroom/articles/{id}", { params: { id } });
}

export function getNewsroomSummary(): Promise<NewsroomSummary> {
  return apiRequest<NewsroomSummary>("GET /api/v1/newsroom/summary");
}

export function setArticleReview(id: string, status: ReviewStatus, note?: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("PATCH /api/v1/newsroom/articles/{id}/review", {
    params: { id },
    body: { status, note: note?.trim() || null },
  });
}

export function retryNewsroomArticle(id: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("POST /api/v1/newsroom/articles/{id}/retry", { params: { id } });
}

/* ------------------------------------------------------------------ story-to-air workflow */

export function listStories(q: StoryQuery = {}, signal?: AbortSignal): Promise<StoryPage> {
  return apiRequest<StoryPage>("GET /api/v1/newsroom/stories", {
    signal,
    query: { page: q.page, page_size: q.pageSize, stage: q.stage, assignee_id: q.assigneeId, q: q.q },
  });
}

export function getStory(id: string): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("GET /api/v1/newsroom/stories/{id}", { params: { id } });
}

/** Take an article (or start an original story). Reporters take stories for themselves. */
export function takeStory(input: TakeStoryInput): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories", {
    body: {
      source_item_id: input.sourceItemId ?? null,
      title: input.title?.trim() || null,
      assignee_id: input.assigneeId ?? null,
      deadline_at: input.deadlineAt ?? null,
      follows_story_id: input.followsStoryId ?? null,
    },
  });
}

export function updateStory(
  id: string,
  changes: { title?: string; assigneeId?: string; deadlineAt?: string | null },
): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("PATCH /api/v1/newsroom/stories/{id}", {
    params: { id },
    body: {
      ...(changes.title !== undefined ? { title: changes.title } : {}),
      ...(changes.assigneeId !== undefined ? { assignee_id: changes.assigneeId } : {}),
      ...(changes.deadlineAt !== undefined ? { deadline_at: changes.deadlineAt } : {}),
    },
  });
}

export function verifyStory(id: string, note: string): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/verify", { params: { id }, body: { note } });
}

/** Save a new script version. `baseVersion` is the version on screen (null for the first script). */
export function saveScript(
  id: string,
  input: { headline: string; body: string; baseVersion: number | null },
): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/scripts", {
    params: { id },
    body: { headline: input.headline, body: input.body, base_version: input.baseVersion },
  });
}

/** Ask the AI for a first draft. Only ever called from a button; the reporter edits the result. */
export function draftScript(id: string, input: { baseVersion: number | null; targetSeconds?: number }): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/scripts/draft", {
    params: { id },
    body: { base_version: input.baseVersion, target_seconds: input.targetSeconds ?? null },
  });
}

export function submitStory(id: string): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/submit", { params: { id } });
}

export function reviewStory(
  id: string,
  input: { decision: StoryDecision; scriptVersion: number; comment?: string },
): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/review", {
    params: { id },
    body: { decision: input.decision, script_version: input.scriptVersion, comment: input.comment?.trim() || null },
  });
}

export function dropStory(id: string): Promise<StoryDetail> {
  return apiRequest<StoryDetail>("POST /api/v1/newsroom/stories/{id}/drop", { params: { id } });
}

export function listAssignees(): Promise<Assignee[]> {
  return apiRequest<Assignee[]>("GET /api/v1/newsroom/assignees");
}

/* ------------------------------------------------------------------ radio bulletins */

export function listBulletins(
  q: { page?: number; pageSize?: number; q?: string; scheduledFrom?: string; aired?: boolean; order?: "asc" | "desc" } = {},
  signal?: AbortSignal,
): Promise<BulletinPage> {
  return apiRequest<BulletinPage>("GET /api/v1/newsroom/bulletins", {
    signal,
    query: { page: q.page, page_size: q.pageSize, q: q.q, scheduled_from: q.scheduledFrom, aired: q.aired, order: q.order },
  });
}

export function getBulletin(id: string): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("GET /api/v1/newsroom/bulletins/{id}", { params: { id } });
}

export function createBulletin(input: { name: string; scheduledFor: string; targetSeconds: number }): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins", {
    body: { name: input.name, scheduled_for: input.scheduledFor, target_seconds: input.targetSeconds },
  });
}

/** Start a new draft revision, copying the approved one. The approved revision stays live until this one is approved. */
export function createRevision(id: string): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins/{id}/revisions", { params: { id } });
}

/** Replace the running order of a draft revision. */
export function saveBulletinItems(id: string, number: number, items: BulletinItemDraft[]): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("PUT /api/v1/newsroom/bulletins/{id}/revisions/{number}/items", {
    params: { id, number: String(number) },
    body: {
      items: items.map((i) => ({
        story_id: i.storyId,
        script_id: i.scriptId,
        duration_override_seconds: i.durationOverrideSeconds,
        note: i.note.trim() || null,
      })),
    },
  });
}

export function submitRevision(id: string, number: number): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/submit", {
    params: { id, number: String(number) },
  });
}

export function approveRevision(id: string, number: number, comment?: string): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/approve", {
    params: { id, number: String(number) },
    body: { comment: comment?.trim() || null },
  });
}

export function rejectRevision(id: string, number: number, comment: string): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/reject", {
    params: { id, number: String(number) },
    body: { comment },
  });
}

/** Record that the approved revision went to air. Its stories become Broadcast and their articles Used. */
export function broadcastBulletin(id: string): Promise<BulletinDetail> {
  return apiRequest<BulletinDetail>("POST /api/v1/newsroom/bulletins/{id}/broadcast", { params: { id } });
}

/**
 * The studio screen's authoritative check. The server answers with the approved version to read and whether a
 * newer one is waiting. Requests are sent with `cache: "no-store"` (see `apiRequest`), so this is never an old answer.
 */
export function getStudio(id: string, signal?: AbortSignal): Promise<StudioView> {
  return apiRequest<StudioView>("GET /api/v1/newsroom/bulletins/{id}/studio", { params: { id }, signal });
}

/* ------------------------------------------------------------------ archive */

export function searchArchive(q: ArchiveQuery = {}, signal?: AbortSignal): Promise<ArchivePage<ArchiveStory>> {
  return apiRequest<ArchivePage<ArchiveStory>>("GET /api/v1/newsroom/archive", {
    signal,
    query: { page: q.page, page_size: q.pageSize, q: q.q, aired_from: q.airedFrom, aired_to: q.airedTo, category: q.category },
  });
}

export function getArchivedStory(id: string): Promise<ArchiveStoryDetail> {
  return apiRequest<ArchiveStoryDetail>("GET /api/v1/newsroom/archive/stories/{id}", { params: { id } });
}

export function searchArchivedBulletins(q: ArchiveQuery = {}, signal?: AbortSignal): Promise<ArchivePage<ArchiveBulletin>> {
  return apiRequest<ArchivePage<ArchiveBulletin>>("GET /api/v1/newsroom/archive/bulletins", {
    signal,
    query: { page: q.page, page_size: q.pageSize, q: q.q, aired_from: q.airedFrom, aired_to: q.airedTo },
  });
}

/** Exactly what went to air in one revision, with the script text that was read. */
export function getArchivedBulletin(id: string, number: number): Promise<ArchiveBulletinDetail> {
  return apiRequest<ArchiveBulletinDetail>("GET /api/v1/newsroom/archive/bulletins/{id}/revisions/{number}", {
    params: { id, number: String(number) },
  });
}
