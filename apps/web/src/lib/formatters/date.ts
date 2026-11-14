import { DEMO_NOW } from "@/lib/mock/clock";
import { isMockMode } from "@/lib/api/config";

const TZ = "Africa/Harare"; // Central Africa Time, UTC+2, no daylight saving.

const shortFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const timeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dayFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  day: "numeric",
  month: "short",
});
const dayLongFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const fullFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const timeSecondsFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const weekdayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short" });

const valid = (iso: string | null | undefined): iso is string => !!iso && !Number.isNaN(new Date(iso).getTime());

/** "3 Nov, 14:52" */
export function formatShort(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? shortFmt.format(new Date(iso)) : fallback;
}

/** "3 Nov 2026, 14:52 CAT" */
export function formatFull(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? `${fullFmt.format(new Date(iso))} CAT` : fallback;
}

/** "14:52" */
export function formatTime(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? timeFmt.format(new Date(iso)) : fallback;
}

/** "14:52:07": for places where seconds matter, such as when the studio screen last heard from the server. */
export function formatTimeSeconds(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? timeSecondsFmt.format(new Date(iso)) : fallback;
}

/** "3 Nov" */
export function formatDay(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? dayFmt.format(new Date(iso)) : fallback;
}

/** "Tuesday, 3 November 2026" */
export function formatDayLong(iso: string | null | undefined): string {
  return valid(iso) ? dayLongFmt.format(new Date(iso)) : "";
}

/** "Sun, 16:40" for recent items, matching the concept's feed rows. */
export function formatWeekdayTime(iso: string | null | undefined, fallback = "Not stated"): string {
  return valid(iso) ? `${weekdayFmt.format(new Date(iso))}, ${timeFmt.format(new Date(iso))}` : fallback;
}

/** "2026-11-03" in Harare time, for date-range arithmetic. */
export function harareDateKey(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));
  return parts;
}

/**
 * The clock used for relative times. In mock mode it is the fixed demo snapshot
 * (so "1 h 35 min ago" is stable and matches the data); in api mode it is real time.
 */
export function referenceNow(): Date {
  return isMockMode() ? DEMO_NOW : new Date();
}

/** "1 h 35 min ago", "Yesterday, 19:20", "3 days ago". */
export function formatRelative(iso: string | null | undefined, fallback = "Not stated"): string {
  if (!valid(iso)) return fallback;
  const diffMin = Math.round((referenceNow().getTime() - new Date(iso).getTime()) / 60_000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffMin < 6 * 60) {
    const h = Math.floor(diffMin / 60);
    const m = diffMin % 60;
    return m ? `${h} h ${m} min ago` : `${h} h ago`;
  }
  // Compare calendar days in Harare time, not elapsed 24-hour blocks.
  const days = Math.round(
    (Date.parse(harareDateKey(referenceNow().toISOString())) - Date.parse(harareDateKey(iso))) / 86_400_000,
  );
  if (days <= 0) return `Today, ${formatTime(iso)}`;
  if (days === 1) return `Yesterday, ${formatTime(iso)}`;
  return `${days} days ago`;
}

/** "4.2 s", "1 min 5 s". */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "–";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const min = Math.floor(s / 60);
  return `${min} min ${Math.round(s - min * 60)} s`;
}

export function formatPercent(value: number | null | undefined): string {
  return value == null ? "–" : `${Math.round(value * 100)}%`;
}

export function formatInterval(seconds: number): string {
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}
