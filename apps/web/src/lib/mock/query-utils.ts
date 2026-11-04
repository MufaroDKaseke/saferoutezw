import type { Paginated } from "@/types";
import type { DateRangeKey, PageQuery } from "@/lib/api/types";
import { DEMO_NOW } from "./clock";

const RANGE_MS: Record<Exclude<DateRangeKey, "all">, number> = {
  "24h": 24 * 3_600_000,
  "7d": 7 * 24 * 3_600_000,
  "30d": 30 * 24 * 3_600_000,
};

/** Start of a range relative to the demo clock, or null for "all time". */
export function rangeStart(range: DateRangeKey | undefined, now: Date = DEMO_NOW): number | null {
  if (!range || range === "all") return null;
  return now.getTime() - RANGE_MS[range];
}

export function inRange(iso: string | null, range: DateRangeKey | undefined): boolean {
  const start = rangeStart(range);
  if (start === null) return true;
  if (!iso) return false;
  return new Date(iso).getTime() >= start;
}

export function matchesSearch(search: string | undefined, ...fields: (string | null | undefined)[]): boolean {
  const needle = search?.trim().toLowerCase();
  if (!needle) return true;
  return fields.some((f) => f?.toLowerCase().includes(needle));
}

type Getter<T> = (item: T) => string | number | null | undefined;

export function sortItems<T>(
  items: T[],
  getters: Record<string, Getter<T>>,
  sort: string | undefined,
  dir: "asc" | "desc" | undefined,
  fallback: { sort: string; dir: "asc" | "desc" },
): T[] {
  const key = sort && getters[sort] ? sort : fallback.sort;
  const direction = sort && getters[sort] ? (dir ?? "asc") : fallback.dir;
  const get = getters[key];
  const factor = direction === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    // Nulls always sort last regardless of direction.
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
    return String(av).localeCompare(String(bv)) * factor;
  });
}

export function paginate<T>(items: T[], q: PageQuery): Paginated<T> {
  const pageSize = Math.max(1, q.pageSize ?? 10);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const page = Math.min(Math.max(1, q.page ?? 1), totalPages);
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize),
    total: items.length,
    page,
    pageSize,
  };
}

/** Simulated network latency so loading states are visible in mock mode. */
export function delay<T>(value: () => T, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      try {
        resolve(value());
      } catch (error) {
        reject(error);
      }
    }, ms);
  });
}
