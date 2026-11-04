/**
 * Fixed "now" for the demo dataset: Tuesday 3 November 2026, 16:27 CAT.
 * Using a fixed instant (not Date.now()) keeps server and client renders
 * identical, keeps relative times stable, and is honest: the demo data is a
 * snapshot, not a live feed.
 */
export const DEMO_NOW = new Date("2026-11-03T16:27:00+02:00");
export const DEMO_NOW_ISO = DEMO_NOW.toISOString();

/** Parse a Central Africa Time wall-clock string such as "2026-11-03 14:52". */
export function cat(wallClock: string): string {
  const [date, time = "00:00"] = wallClock.trim().split(/[ T]/);
  return new Date(`${date}T${time}:00+02:00`).toISOString();
}

/** Minutes before the demo "now", as an ISO string. */
export function minutesAgo(minutes: number): string {
  return new Date(DEMO_NOW.getTime() - minutes * 60_000).toISOString();
}

/** Deterministic PRNG (mulberry32) so generated fixtures never change between renders. */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Great-circle distance in kilometres. */
export function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
