import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { IngestionRun, SourceSummary } from "@/types";
import { dual, route } from "./client";
import { listIngestionHistoryLive, listSourcesLive } from "./live/queries";
import type { ActionResult, SourceInput, SourceTestResult } from "./types";

export function listSources(): Promise<SourceSummary[]> {
  return dual({ mock: () => mock.listSources(), live: () => listSourcesLive() });
}

export function listIngestionHistory(sourceId: string): Promise<IngestionRun[]> {
  return dual({ mock: () => mock.listIngestionHistory(sourceId), live: () => listIngestionHistoryLive(sourceId) });
}

export function createSource(input: SourceInput): Promise<ActionResult<SourceSummary>> {
  return route({ endpoint: "POST /api/v1/sources", body: input, mock: () => actions.createSource(input) });
}

export function updateSource(
  id: string,
  patch: Partial<SourceInput> & { enabled?: boolean },
): Promise<ActionResult<SourceSummary>> {
  return route({
    endpoint: "PATCH /api/v1/sources/{id}",
    body: patch,
    mock: () => actions.updateSource(id, patch),
  });
}

export function testSource(id: string): Promise<ActionResult<SourceTestResult>> {
  return route({ endpoint: "POST /api/v1/sources/{id}/test", mock: () => actions.testSource(id) });
}

export function triggerPoll(id: string): Promise<ActionResult<IngestionRun>> {
  return route({ endpoint: "POST /api/v1/sources/{id}/poll", mock: () => actions.triggerPoll(id) });
}
