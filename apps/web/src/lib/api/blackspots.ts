import * as mock from "@/lib/mock/queries";
import type { Blackspot, Paginated } from "@/types";
import { dual } from "./client";
import { listBlackspotsLive } from "./live/queries";
import type { BlackspotQuery } from "./types";

export function listBlackspots(query: BlackspotQuery): Promise<Paginated<Blackspot>> {
  return dual({ mock: () => mock.listBlackspots(query), live: () => listBlackspotsLive(query) });
}
