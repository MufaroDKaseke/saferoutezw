import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { ChannelDelivery, ChannelKind, Paginated, PublicAlert } from "@/types";
import type { components } from "./schema";
import { apiRequest, dual, route } from "./client";
import type { ActionResult, AlertQuery } from "./types";

type LiveAlert = components["schemas"]["AlertOut"];
type LivePage = components["schemas"]["Page_AlertOut_"];

/** Newsroom alerts are real in API mode: every approved incident is listed, publishing is one click. */
function mapAlert(a: LiveAlert): PublicAlert {
  const channels: ChannelDelivery[] = a.channels.map((c) => ({
    channel: c.channel as ChannelKind,
    status: c.status,
    maxAttempts: c.max_attempts,
    lastError: c.last_error,
    attempts: [
      {
        id: `${a.id}-web-1`,
        attemptNumber: 1,
        status: "succeeded" as const,
        attemptedAt: a.published_at ?? a.approved_at,
        error: null,
      },
    ],
  }));
  return {
    id: a.id,
    reference: a.reference,
    incidentId: a.incident_id,
    incidentReference: a.incident_reference,
    incidentType: a.incident_type as PublicAlert["incidentType"],
    locationText: a.location_text,
    bulletinVersionId: a.bulletin_version_id,
    bulletinVersionNumber: a.bulletin_version_number,
    headline: a.headline,
    body: a.body,
    approvalReviewId: a.approval_review_id,
    approvedByName: a.approved_by_name,
    approvedAt: a.approved_at,
    status: a.status,
    publishedAt: a.published_at,
    publicationState: a.publication_state,
    channels,
  };
}

export function listAlerts(query: AlertQuery): Promise<Paginated<PublicAlert>> {
  return dual({
    mock: () => mock.listAlerts(query),
    live: async () => {
      const data = await apiRequest<LivePage>("GET /api/v1/alerts", {
        query: { search: query.search, state: query.state, page: query.page, page_size: query.pageSize },
      });
      return { items: data.items.map(mapAlert), total: data.total, page: data.page, pageSize: data.page_size };
    },
  });
}

export function getAlert(id: string): Promise<PublicAlert> {
  return dual({
    mock: () => mock.getAlert(id),
    live: async () => mapAlert(await apiRequest<LiveAlert>("GET /api/v1/alerts/{id}", { params: { id } })),
  });
}

export function getAwaitingApprovalCount(): Promise<number> {
  return route({ endpoint: "GET /api/v1/alerts/awaiting-approval", mock: () => mock.countAwaitingApproval() });
}

/**
 * One-click publication of the incident's latest approved bulletin. The server re-checks the
 * approval, that the version is still the latest, and that it holds no personal details.
 */
export function publishAlert(id: string): Promise<ActionResult> {
  return dual({
    mock: () => actions.publishAlert(id),
    live: async () => {
      await apiRequest<LiveAlert>("POST /api/v1/alerts/{id}/publish", { params: { id }, body: {} });
      return { simulated: false, message: "Published. The alert is now visible on the public site." };
    },
  });
}

export function unpublishAlert(id: string, reason?: string): Promise<ActionResult> {
  return dual({
    mock: () => {
      throw new Error("Unpublishing is not part of the demo.");
    },
    live: async () => {
      await apiRequest<LiveAlert>("POST /api/v1/alerts/{id}/unpublish", { params: { id }, body: { reason } });
      return { simulated: false, message: "Unpublished. The alert is no longer visible on the public site." };
    },
  });
}

export function retryDelivery(id: string, channel: ChannelKind): Promise<ActionResult> {
  return route({
    endpoint: "POST /api/v1/alerts/{id}/retry",
    body: { channel },
    mock: () => actions.retryDelivery(id, channel),
  });
}
