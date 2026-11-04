import * as mock from "@/lib/mock/queries";
import type { AuditEvent, Incident, IncidentDetail, Paginated } from "@/types";
import { route } from "./client";
import type { IncidentQuery, MapQuery } from "./types";

export type { MapData } from "@/lib/mock/queries";

export function listIncidents(query: IncidentQuery): Promise<Paginated<Incident>> {
  return route({ endpoint: "GET /api/v1/incidents", query, mock: () => mock.listIncidents(query) });
}

export function getIncident(id: string): Promise<{ incident: IncidentDetail; history: AuditEvent[] }> {
  return route({
    endpoint: "GET /api/v1/incidents/{id}",
    mock: () => ({ incident: mock.getIncident(id), history: mock.getIncidentAudit(id) }),
  });
}

export function getMapData(query: MapQuery): Promise<mock.MapData> {
  return route({ endpoint: "GET /api/v1/map", query, mock: () => mock.listMapData(query) });
}
