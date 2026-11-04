/**
 * API-mode editorial actions. The browser only sends the request: the reviewer is the
 * signed-in session (never a field we send), FastAPI checks the role and the bulletin
 * version, and PostgreSQL triggers re-check. A rejected request surfaces as an ApiError.
 */
import { apiRequest } from "../client";
import type { components } from "../schema";
import type { ActionResult } from "../types";

type S = components["schemas"];
type BulletinPage = { items: S["BulletinOut"][] };

export interface LiveDraftInput {
  headline: string;
  body: string;
  notes?: string;
}

async function latestBulletin(incidentId: string): Promise<S["BulletinOut"] | null> {
  const page = await apiRequest<BulletinPage>("GET /api/v1/incidents/{id}/bulletins", {
    params: { id: incidentId },
    query: { page_size: 1 },
  });
  return page.items[0] ?? null;
}

/**
 * Save the text as a new immutable version, unless it is identical to the latest one.
 * `base_version` makes a concurrent edit by someone else a 409 instead of a silent overwrite.
 */
async function ensureVersion(incidentId: string, input: LiveDraftInput): Promise<S["BulletinOut"]> {
  const latest = await latestBulletin(incidentId);
  if (latest && latest.headline === input.headline.trim() && latest.body === input.body.trim()) return latest;
  return apiRequest<S["BulletinOut"]>("POST /api/v1/incidents/{id}/bulletins", {
    params: { id: incidentId },
    body: { headline: input.headline, body: input.body, base_version: latest?.version_number ?? null },
  });
}

export async function saveDraftLive(
  incidentId: string,
  input: LiveDraftInput,
): Promise<ActionResult<{ versionNumber: number }>> {
  const version = await ensureVersion(incidentId, input);
  return { simulated: false, message: `Draft saved as bulletin version ${version.version_number}.`, data: { versionNumber: version.version_number } };
}

async function decide(
  incidentId: string,
  decision: "approved" | "rejected" | "needs_changes",
  bulletinVersionId: string | null,
  notes: string | null,
): Promise<S["ReviewResult"]> {
  return apiRequest<S["ReviewResult"]>("POST /api/v1/incidents/{id}/reviews", {
    params: { id: incidentId },
    body: { decision, bulletin_version_id: bulletinVersionId, notes },
  });
}

export async function requestChangesLive(incidentId: string, notes: string): Promise<ActionResult> {
  await decide(incidentId, "needs_changes", null, notes);
  return { simulated: false, message: "Changes requested. The incident stays in the queue." };
}

export async function rejectLive(incidentId: string, reason: string): Promise<ActionResult> {
  await decide(incidentId, "rejected", null, reason);
  return { simulated: false, message: "Incident rejected. The decision is recorded in its review history." };
}

export async function approveLive(
  incidentId: string,
  input: LiveDraftInput,
): Promise<ActionResult<{ alertId: string | null; versionNumber: number }>> {
  const version = await ensureVersion(incidentId, input);
  await decide(incidentId, "approved", version.id, input.notes?.trim() || null);
  return {
    simulated: false,
    message: `Approved bulletin version ${version.version_number}. It is now in Alerts, ready for an editor to publish.`,
    data: { alertId: incidentId, versionNumber: version.version_number },
  };
}

export type LocationAction =
  | { action: "accept_proposed"; note?: string }
  | { action: "select_candidate"; candidateIndex: number; note?: string }
  | { action: "set_coordinates"; latitude: number; longitude: number; precisionMeters?: number; note?: string }
  | { action: "mark_unresolved"; note?: string };

export async function confirmLocationLive(incidentId: string, input: LocationAction): Promise<S["LocationOut"]> {
  const body: Record<string, unknown> = { action: input.action, note: input.note };
  if (input.action === "select_candidate") body.candidate_index = input.candidateIndex;
  if (input.action === "set_coordinates") {
    body.latitude = input.latitude;
    body.longitude = input.longitude;
    body.precision_meters = input.precisionMeters;
  }
  return apiRequest<S["LocationOut"]>("POST /api/v1/incidents/{id}/location/confirm", {
    params: { id: incidentId },
    body,
  });
}
