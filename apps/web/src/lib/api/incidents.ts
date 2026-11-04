import * as mock from "@/lib/mock/queries";
import type { AuditEvent, Incident, IncidentDetail, Paginated } from "@/types";
import { dual } from "./client";
import { getIncidentLive, getMapDataLive, listIncidentsLive } from "./live/queries";
import type { IncidentQuery, MapQuery } from "./types";

export type { MapData } from "@/lib/mock/queries";

export function listIncidents(query: IncidentQuery): Promise<Paginated<Incident>> {
  return dual({ mock: () => mock.listIncidents(query), live: () => listIncidentsLive(query) });
}

export function getIncident(id: string): Promise<{ incident: IncidentDetail; history: AuditEvent[] }> {
  return dual({
    mock: () => ({ incident: mock.getIncident(id), history: mock.getIncidentAudit(id) }),
    live: () => getIncidentLive(id),
  });
}

export function getMapData(query: MapQuery): Promise<mock.MapData> {
  return dual({ mock: () => mock.listMapData(query), live: () => getMapDataLive(query) });
}
