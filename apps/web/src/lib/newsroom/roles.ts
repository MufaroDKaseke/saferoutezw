import { APP_MODE, type AppMode } from "@/lib/app-mode";
import type { UserRole } from "@/types";

/**
 * Newsroom roles. The server enforces every one of these; the web app only decides what to show.
 *
 * `editor` is the Executive Producer in the newsroom. Who may approve is one constant on each side:
 * `APPROVER_ROLES` here mirrors `APPROVER_ROLES` in `apps/api/app/api/deps.py` and must change with it.
 */
export const EXECUTIVE_PRODUCER = "Executive Producer";

export const APPROVER_ROLES: readonly UserRole[] = ["admin", "editor"];
export const STORY_WRITE_ROLES: readonly UserRole[] = ["admin", "editor", "reporter"];

export const canApprove = (role: UserRole | null | undefined): boolean => !!role && APPROVER_ROLES.includes(role);
export const canWriteStories = (role: UserRole | null | undefined): boolean => !!role && STORY_WRITE_ROLES.includes(role);

const ROLE_TITLES: Record<UserRole, string> = {
  admin: "Administrator",
  editor: "Editor",
  analyst: "Analyst",
  reporter: "Reporter",
  contributor: "Contributor",
  service: "Service account",
};

/** The title shown for a role. In the newsroom the `editor` role is the Executive Producer, everywhere. */
export function roleTitle(role: UserRole, mode: AppMode = APP_MODE): string {
  return role === "editor" && mode === "nust_newsroom" ? EXECUTIVE_PRODUCER : ROLE_TITLES[role];
}
