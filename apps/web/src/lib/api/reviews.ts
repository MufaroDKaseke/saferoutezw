import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, ReviewQueueItem, ReviewWorkspace } from "@/types";
import { apiRequest, dual } from "./client";
import { fetchSession } from "./auth";
import {
  approveLive,
  confirmLocationLive,
  rejectLive,
  requestChangesLive,
  saveDraftLive,
  type LocationAction,
} from "./live/actions";
import {
  getPendingReviewCountLive,
  getReviewCountsLive,
  getReviewWorkspaceLive,
  listReviewsLive,
} from "./live/queries";
import type { ActionResult, ReviewQuery } from "./types";

export type { DraftInput } from "@/lib/mock/actions";
export type { LocationAction } from "./live/actions";

export function listReviews(query: ReviewQuery): Promise<Paginated<ReviewQueueItem>> {
  return dual({ mock: () => mock.listReviews(query), live: () => listReviewsLive(query) });
}

export function getReviewCounts() {
  return dual({ mock: () => mock.getReviewCounts(), live: () => getReviewCountsLive() });
}

export function getPendingReviewCount(): Promise<number> {
  return dual({ mock: () => mock.getPendingReviewCount(), live: () => getPendingReviewCountLive() });
}

export function getReviewWorkspace(incidentId: string): Promise<ReviewWorkspace> {
  return dual({
    mock: () => mock.getReviewWorkspace(incidentId),
    live: async () => getReviewWorkspaceLive(incidentId, (await fetchSession())?.role ?? null),
  });
}

/*
 * Decisions. In api mode these are validated by FastAPI (role, bulletin version, status)
 * and re-checked by the PostgreSQL triggers; the browser only sends the request and the
 * reviewer is always the signed-in session. In mock mode they change local demo state and
 * report `simulated: true`.
 */

export function saveDraft(
  incidentId: string,
  input: actions.DraftInput,
): Promise<ActionResult<{ versionNumber: number }>> {
  return dual({ mock: () => actions.saveDraft(incidentId, input), live: () => saveDraftLive(incidentId, input) });
}

export function requestChanges(incidentId: string, notes: string): Promise<ActionResult> {
  return dual({
    mock: () => actions.requestChanges(incidentId, notes),
    live: () => requestChangesLive(incidentId, notes),
  });
}

export function rejectIncident(incidentId: string, reason: string): Promise<ActionResult> {
  return dual({ mock: () => actions.rejectIncident(incidentId, reason), live: () => rejectLive(incidentId, reason) });
}

export function approveIncident(
  incidentId: string,
  input: actions.DraftInput,
): Promise<ActionResult<{ alertId: string | null; versionNumber: number }>> {
  return dual({ mock: () => actions.approveIncident(incidentId, input), live: () => approveLive(incidentId, input) });
}

/** Editor decision about where an incident happened. API mode only. */
export function confirmLocation(incidentId: string, input: LocationAction) {
  return confirmLocationLive(incidentId, input);
}

export interface SummaryDraft {
  summary: string;
  model: string;
  sourcesUsed: number;
  notice: string;
  simulated: boolean;
}

/**
 * Ask the server for an AI-drafted summary of the whole story. The draft is returned as text only:
 * nothing is saved or published until the editor reviews, saves and approves it.
 */
export function generateSummary(incidentId: string, title: string): Promise<SummaryDraft> {
  return dual<SummaryDraft>({
    mock: () => ({
      summary: `[Demo draft] ${title}. In demo mode no AI is called.`,
      model: "demo",
      sourcesUsed: 0,
      notice: "Demo mode: this is placeholder text, not an AI summary.",
      simulated: true,
    }),
    live: async () => {
      const data = await apiRequest<{ summary: string; model: string; sources_used: number; notice: string }>(
        "POST /api/v1/incidents/{id}/summary",
        { params: { id: incidentId } },
      );
      return { summary: data.summary, model: data.model, sourcesUsed: data.sources_used, notice: data.notice, simulated: false };
    },
  });
}
