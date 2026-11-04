import { describe, expect, it } from "vitest";
import { cat } from "@/lib/mock/clock";
import { formatDuration, formatRelative, formatShort, formatTime } from "./date";

// The demo clock is fixed at Tue 3 Nov 2026, 16:27 CAT.
describe("formatRelative", () => {
  it("uses minutes and hours for recent items", () => {
    expect(formatRelative(cat("2026-11-03 16:23"))).toBe("4 min ago");
    expect(formatRelative(cat("2026-11-03 14:52"))).toBe("1 h 35 min ago");
  });

  it("compares calendar days in Harare time, not 24-hour blocks", () => {
    // 19 hours ago, but on the previous calendar day.
    expect(formatRelative(cat("2026-11-02 21:15"))).toBe("Yesterday, 21:15");
    expect(formatRelative(cat("2026-11-01 16:40"))).toBe("2 days ago");
  });

  it("falls back for missing or invalid dates", () => {
    expect(formatRelative(null)).toBe("Not stated");
    expect(formatRelative("nonsense", "n/a")).toBe("n/a");
  });
});

describe("formatters", () => {
  it("shows Central Africa Time", () => {
    expect(formatShort("2026-11-03T12:52:00Z")).toBe("3 Nov, 14:52");
    expect(formatTime("2026-11-03T12:52:00Z")).toBe("14:52");
  });

  it("formats durations", () => {
    expect(formatDuration(null)).toBe("–");
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(4200)).toBe("4.2 s");
    expect(formatDuration(65_000)).toBe("1 min 5 s");
  });
});
