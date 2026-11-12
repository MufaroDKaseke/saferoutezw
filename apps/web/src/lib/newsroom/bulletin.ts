import { formatClock } from "./reading-time";
import type { BulletinItemDraft, BulletinRevision, StorySummary } from "./types";

/**
 * One row of the running order as the builder edits it. `scriptId: null` means "let the server pick": the
 * story's approved script, or its newest if none is approved yet. `saved` is false for a row added in the
 * browser that the server has not pinned yet.
 */
export interface BuilderRow {
  storyId: string;
  title: string;
  stage: string;
  scriptId: string | null;
  scriptVersion: number | null;
  approved: boolean;
  newerScriptVersion: number | null;
  /** The script's reading-time estimate, in seconds. */
  seconds: number;
  /** A clip's duration, replacing the estimate. */
  overrideSeconds: number | null;
  note: string;
  saved: boolean;
}

export function rowsFromRevision(revision: BulletinRevision): BuilderRow[] {
  return revision.items.map((i) => ({
    storyId: i.story.id,
    title: i.story.title,
    stage: i.story.stage,
    scriptId: i.script.id,
    scriptVersion: i.script.version_number,
    approved: i.script_approved,
    newerScriptVersion: i.newer_script_version,
    seconds: i.script.estimated_seconds,
    overrideSeconds: i.duration_overridden ? i.duration_seconds : null,
    note: i.note ?? "",
    saved: true,
  }));
}

/** A story picked for the bulletin: pinned by the server on save (its approved script, else its newest). */
export function rowFromStory(story: StorySummary): BuilderRow {
  return {
    storyId: story.id,
    title: story.title,
    stage: story.stage,
    scriptId: null,
    scriptVersion: story.approved_script_version ?? story.latest_script_version,
    approved: story.approved_script_version !== null,
    newerScriptVersion: null,
    seconds: story.latest_script_seconds ?? 0,
    overrideSeconds: null,
    note: "",
    saved: false,
  };
}

export const rowSeconds = (row: BuilderRow): number => row.overrideSeconds ?? row.seconds;

export const totalSeconds = (rows: BuilderRow[]): number => rows.reduce((sum, r) => sum + rowSeconds(r), 0);

export function toDrafts(rows: BuilderRow[]): BulletinItemDraft[] {
  return rows.map((r) => ({ storyId: r.storyId, scriptId: r.scriptId, durationOverrideSeconds: r.overrideSeconds, note: r.note }));
}

/** Move a row up (-1) or down (+1). Out-of-range moves return the list unchanged. */
export function moveRow<T>(rows: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (index < 0 || index >= rows.length || target < 0 || target >= rows.length) return rows;
  const next = [...rows];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export interface TimeStatus {
  state: "under" | "over" | "on";
  /** Seconds away from the target (always positive). */
  difference: number;
  /** In words, so colour never carries the meaning alone: "0:30 under target". */
  label: string;
  /** How full the bar is, 0 to 100. */
  percent: number;
}

export function timeVersusTarget(total: number, target: number): TimeStatus {
  const difference = Math.abs(target - total);
  const state = total === target ? "on" : total > target ? "over" : "under";
  return {
    state,
    difference,
    label: state === "on" ? "On target" : `${formatClock(difference)} ${state} target`,
    percent: target > 0 ? Math.min(100, Math.round((total / target) * 100)) : 0,
  };
}

/** The revision a builder opens on: the one being worked on, else the live one, else the newest. */
export function defaultRevision(revisions: BulletinRevision[], approvedNumber: number | null): BulletinRevision {
  return (
    revisions.find((r) => r.state === "draft" || r.state === "pending_approval") ??
    revisions.find((r) => r.revision_number === approvedNumber) ??
    revisions[revisions.length - 1]
  );
}
