import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, ReviewQueueItem, ReviewWorkspace } from "@/types";
import { route } from "./client";
import type { ActionResult, ReviewQuery } from "./types";

export type { DraftInput } from "@/lib/mock/actions";

export function listReviews(query: ReviewQuery): Promise<Paginated<ReviewQueueItem>> {
  return route({ endpoint: "GET /api/v1/reviews", query, mock: () => mock.listReviews(query) });
}

export function getReviewCounts() {
  return route({ endpoint: "GET /api/v1/reviews/counts", mock: () => mock.getReviewCounts() });
}

export function getPendingReviewCount(): Promise<number> {
  return route({ endpoint: "GET /api/v1/reviews/pending-count", mock: () => mock.getPendingReviewCount() });
}

export function getReviewWorkspace(incidentId: string): Promise<ReviewWorkspace> {
  return route({
    endpoint: "GET /api/v1/reviews/{id}",
    mock: () => mock.getReviewWorkspace(incidentId),
  });
}

/*
 * Decisions. In api mode these must be validated by FastAPI and enforced by the
 * PostgreSQL triggers; the browser only sends the request. In mock mode they
 * change local demo state and report `simulated: true`.
 */

export function saveDraft(
  incidentId: string,
  input: actions.DraftInput,
): Promise<ActionResult<{ versionNumber: number }>> {
  return route({
    endpoint: "POST /api/v1/reviews/{id}/draft",
    body: input,
    mock: () => actions.saveDraft(incidentId, input),
  });
}

export function requestChanges(incidentId: string, notes: string): Promise<ActionResult> {
  return route({
    endpoint: "POST /api/v1/reviews/{id}/request-changes",
    body: { notes },
    mock: () => actions.requestChanges(incidentId, notes),
  });
}

export function rejectIncident(incidentId: string, reason: string): Promise<ActionResult> {
  return route({
    endpoint: "POST /api/v1/reviews/{id}/reject",
    body: { reason },
    mock: () => actions.rejectIncident(incidentId, reason),
  });
}

export function approveIncident(
  incidentId: string,
  input: actions.DraftInput,
): Promise<ActionResult<{ alertId: string; versionNumber: number }>> {
  return route({
    endpoint: "POST /api/v1/reviews/{id}/approve",
    body: input,
    mock: () => actions.approveIncident(incidentId, input),
  });
}
