import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { ChannelKind, Paginated, PublicAlert } from "@/types";
import { route } from "./client";
import type { ActionResult, AlertQuery } from "./types";

export function listAlerts(query: AlertQuery): Promise<Paginated<PublicAlert>> {
  return route({ endpoint: "GET /api/v1/alerts", query, mock: () => mock.listAlerts(query) });
}

export function getAlert(id: string): Promise<PublicAlert> {
  return route({ endpoint: "GET /api/v1/alerts/{id}", mock: () => mock.getAlert(id) });
}

export function getAwaitingApprovalCount(): Promise<number> {
  return route({ endpoint: "GET /api/v1/alerts/awaiting-approval", mock: () => mock.countAwaitingApproval() });
}

/** Distribution is a backend-protected action. In mock mode it only marks local demo state. */
export function publishAlert(id: string): Promise<ActionResult> {
  return route({ endpoint: "POST /api/v1/alerts/{id}/publish", mock: () => actions.publishAlert(id) });
}

export function retryDelivery(id: string, channel: ChannelKind): Promise<ActionResult> {
  return route({
    endpoint: "POST /api/v1/alerts/{id}/retry",
    body: { channel },
    mock: () => actions.retryDelivery(id, channel),
  });
}
