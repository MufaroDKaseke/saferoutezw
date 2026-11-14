/** Words per minute behind a reading-time estimate when the server has not said otherwise. */
export const DEFAULT_READING_WPM = 150;

export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/**
 * Seconds needed to read `text` aloud, rounded up (0 for no words). The same maths as `estimate_seconds` in
 * `apps/api/app/services/newsroom_workflow.py`, so what the editor shows while typing matches what the server
 * stores when the script is saved.
 */
export function estimateSeconds(text: string, wpm: number = DEFAULT_READING_WPM): number {
  const words = countWords(text);
  return words === 0 ? 0 : Math.ceil((words * 60) / wpm);
}

/** "0:30", "5:00", "12:05". */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
