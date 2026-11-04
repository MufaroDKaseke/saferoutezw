import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, ReviewQueueItem, ReviewWorkspace } from "@/types";
import { dual } from "./client";
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
