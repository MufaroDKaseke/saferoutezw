import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, ProcessingBacklog, ProcessingJob } from "@/types";
import { route } from "./client";
import type { ActionResult, ProcessingQuery } from "./types";

export function listProcessing(query: ProcessingQuery): Promise<Paginated<ProcessingJob>> {
  return route({ endpoint: "GET /api/v1/processing", query, mock: () => mock.listProcessing(query) });
}

export function getBacklog(): Promise<ProcessingBacklog> {
  return route({ endpoint: "GET /api/v1/processing/backlog", mock: () => mock.getBacklog() });
}

export function retryJob(id: string): Promise<ActionResult> {
  return route({ endpoint: "POST /api/v1/processing/{id}/retry", mock: () => actions.retryJob(id) });
}
