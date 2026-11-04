import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, ProcessingBacklog, ProcessingJob } from "@/types";
import { dual, route } from "./client";
import { getBacklogLive, listProcessingLive } from "./live/queries";
import type { ActionResult, ProcessingQuery } from "./types";

export function listProcessing(query: ProcessingQuery): Promise<Paginated<ProcessingJob>> {
  return dual({ mock: () => mock.listProcessing(query), live: () => listProcessingLive(query) });
}

export function getBacklog(): Promise<ProcessingBacklog> {
  return dual({ mock: () => mock.getBacklog(), live: () => getBacklogLive() });
}

export function retryJob(id: string): Promise<ActionResult> {
  return route({ endpoint: "POST /api/v1/processing/{id}/retry", mock: () => actions.retryJob(id) });
}
