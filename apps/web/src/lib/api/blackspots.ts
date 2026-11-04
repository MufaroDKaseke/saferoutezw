import * as mock from "@/lib/mock/queries";
import type { Blackspot, Paginated } from "@/types";
import { route } from "./client";
import type { BlackspotQuery } from "./types";

export function listBlackspots(query: BlackspotQuery): Promise<Paginated<Blackspot>> {
  return route({ endpoint: "GET /api/v1/blackspots", query, mock: () => mock.listBlackspots(query) });
}
