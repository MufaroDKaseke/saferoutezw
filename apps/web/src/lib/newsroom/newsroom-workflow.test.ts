import { afterEach, describe, expect, it, vi } from "vitest";
import { NEWSROOM_ROUTE_PREFIXES, isNewsroomRoute, isRouteAllowed } from "@/lib/app-mode";
import { DEFAULT_READING_WPM, countWords, estimateSeconds, formatClock } from "./reading-time";
import { EXECUTIVE_PRODUCER, APPROVER_ROLES, STORY_WRITE_ROLES, canApprove, canWriteStories, roleTitle } from "./roles";
import { BOARD_STAGES, DROPPABLE_STAGES, SCRIPT_EDITABLE_STAGES, STORY_STAGES, STORY_STAGE_LABEL } from "./taxonomy";

describe("reading time", () => {
  it("matches the server: 150 words a minute, rounded up", () => {
    expect(DEFAULT_READING_WPM).toBe(150);
    expect(estimateSeconds("")).toBe(0);
    expect(estimateSeconds("   \n ")).toBe(0);
    expect(estimateSeconds(Array(75).fill("word").join(" "))).toBe(30);
    expect(estimateSeconds("word")).toBe(1);
    expect(estimateSeconds(Array(151).fill("word").join(" "))).toBe(61);
    expect(estimateSeconds(Array(75).fill("word").join(" "), 120)).toBe(38);
  });

  it("counts any whitespace as a word break", () => {
    expect(countWords("two\twords\nacross  lines")).toBe(4);
    expect(countWords("")).toBe(0);
  });

  it("formats a clock time", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(30)).toBe("0:30");
    expect(formatClock(300)).toBe("5:00");
    expect(formatClock(725)).toBe("12:05");
    expect(formatClock(-4)).toBe("0:00");
  });
});

describe("newsroom roles", () => {
  it("calls the editor role the Executive Producer in the newsroom, and only there", () => {
    expect(EXECUTIVE_PRODUCER).toBe("Executive Producer");
    expect(roleTitle("editor", "nust_newsroom")).toBe("Executive Producer");
    expect(roleTitle("editor", "road_safety")).toBe("Editor");
    expect(roleTitle("reporter", "nust_newsroom")).toBe("Reporter");
    expect(roleTitle("admin", "nust_newsroom")).toBe("Administrator");
  });

  it("lets reporters write but never approve", () => {
    expect(canWriteStories("reporter")).toBe(true);
    expect(canApprove("reporter")).toBe(false);
    expect(canApprove("analyst")).toBe(false);
    expect(canWriteStories("analyst")).toBe(false);
    expect(canApprove("editor")).toBe(true);
    expect(canApprove(undefined)).toBe(false);
  });

  it("keeps the approver list in one place that mirrors the server", () => {
    expect([...APPROVER_ROLES]).toEqual(["admin", "editor"]);
    expect([...STORY_WRITE_ROLES]).toEqual(["admin", "editor", "reporter"]);
  });
});

describe("story stages", () => {
  it("labels every stage and keeps broadcast and dropped stories off the board", () => {
    for (const stage of STORY_STAGES) expect(STORY_STAGE_LABEL[stage]).toBeTruthy();
    expect(STORY_STAGE_LABEL.in_review).toBe("Awaiting approval");
    expect(BOARD_STAGES).not.toContain("broadcast");
    expect(BOARD_STAGES).not.toContain("dropped");
    expect([...BOARD_STAGES]).toEqual(["assigned", "drafting", "changes_requested", "in_review", "approved"]);
  });

  it("matches the server rules about what can still change", () => {
    expect(SCRIPT_EDITABLE_STAGES).not.toContain("in_review"); // locked while the Executive Producer decides
    expect(SCRIPT_EDITABLE_STAGES).toContain("approved"); // editing reopens it as a draft
    expect(DROPPABLE_STAGES).not.toContain("broadcast");
    expect(DROPPABLE_STAGES).not.toContain("dropped");
  });
});

describe("newsroom-only routes", () => {
  it.each(["/stories", "/stories/123", "/bulletins", "/bulletins/1", "/studio", "/studio/2", "/archive"])(
    "serves %s in newsroom mode and hides it in road-safety mode",
    (path) => {
      expect(isNewsroomRoute(path)).toBe(true);
      expect(isRouteAllowed(path, "nust_newsroom")).toBe(true);
      expect(isRouteAllowed(path, "road_safety")).toBe(false);
    },
  );

  it("leaves every other page alone in both modes and matches whole segments only", () => {
    for (const path of ["/news", "/dashboard", "/settings", "/sources", "/processing"]) {
      expect(isRouteAllowed(path, "road_safety")).toBe(true);
      expect(isRouteAllowed(path, "nust_newsroom")).toBe(true);
    }
    expect(isNewsroomRoute("/storiesx")).toBe(false);
    expect(isNewsroomRoute("/news/stories")).toBe(false);
    expect(NEWSROOM_ROUTE_PREFIXES).toContain("/stories");
  });
});

describe("story API calls", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("sends a list of stages as repeated query parameters", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "api");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 50 }), { status: 200 }));
    const { listStories } = await import("@/lib/api/newsroom");
    await listStories({ stage: ["in_review", "approved"], pageSize: 50 });
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain("/api/v1/newsroom/stories?");
    expect(url).toContain("stage=in_review&stage=approved");
    expect(url).toContain("page_size=50");
  });

  it("sends the script version being edited so a stale save is refused", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "api");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 201 }));
    const { saveScript, reviewStory } = await import("@/lib/api/newsroom");
    await saveScript("s1", { headline: "H", body: "B", baseVersion: 2 });
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({ headline: "H", body: "B", base_version: 2 });
    await reviewStory("s1", { decision: "approved", scriptVersion: 3, comment: "  ok  " });
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toEqual({ decision: "approved", script_version: 3, comment: "ok" });
  });
});
