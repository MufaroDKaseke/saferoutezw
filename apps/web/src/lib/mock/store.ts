import { buildMockDb, type MockDb } from "./build";
import { DEMO_NOW } from "./clock";

/**
 * In-memory demo database. One module-level instance is shared by every page, so
 * a simulated approval on the review screen shows up on the alerts screen and
 * the map. It resets on a full page reload, by design: nothing is persisted and
 * nothing reaches PostgreSQL.
 */
let db: MockDb = buildMockDb();
let notes: Record<string, string> = {};
let version = 0;
const listeners = new Set<() => void>();
const LOADED_AT = Date.now();

export const getDb = () => db;
export const getNotes = (incidentId: string) => notes[incidentId] ?? "";

/** Demo "now": the fixed snapshot time plus real time elapsed since load. */
export function demoNow(): string {
  return new Date(DEMO_NOW.getTime() + (Date.now() - LOADED_AT)).toISOString();
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const getVersion = () => version;

/** Replace part of the database and notify subscribers (hooks refetch). */
export function update(patch: Partial<MockDb>, noteUpdate?: { incidentId: string; text: string }) {
  db = { ...db, ...patch };
  if (noteUpdate) notes = { ...notes, [noteUpdate.incidentId]: noteUpdate.text };
  version += 1;
  listeners.forEach((l) => l());
}

export function resetMockDb() {
  db = buildMockDb();
  notes = {};
  version += 1;
  listeners.forEach((l) => l());
}
