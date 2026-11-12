import { act, render, renderHook, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  STUDIO_FAILURES_BEFORE_UNCONFIRMED,
  STUDIO_POLL_MS,
  STUDIO_TIMEOUT_MS,
  deriveStudioStatus,
  useStudioStatus,
} from "@/hooks/use-studio-status";
import type { BulletinSummary, StudioView } from "@/lib/newsroom/types";
import { StudioIndex } from "./studio-index";
import { StudioScreen } from "./studio-screen";

const api = vi.hoisted(() => ({ getStudio: vi.fn(), listBulletins: vi.fn() }));
vi.mock("@/lib/api/newsroom", () => api);

const view = (o: Partial<StudioView> = {}): StudioView => ({
  bulletin_id: "b1",
  name: "6pm News",
  scheduled_for: "2099-01-01T16:00:00Z",
  target_seconds: 300,
  status: "approved",
  version: 1,
  approved_at: "2099-01-01T14:00:00Z",
  approved_by: { id: "u-ep", display_name: "Esther Producer" },
  items: [
    { position: 1, story_title: "Budget", headline: "Council approves budget", body: "The council approved its budget on Tuesday.", duration_seconds: 30, duration_overridden: false, note: null },
    { position: 2, story_title: "Dam", headline: "Dam levels fall", body: "Dam levels are down.", duration_seconds: 75, duration_overridden: true, note: "Play clip 3 after the intro" },
  ],
  total_seconds: 105,
  newer_revision_pending: false,
  newer_revision_number: null,
  aired_at: null,
  server_time: "2099-01-01T15:59:30Z",
  ...o,
});

/** Run the clock forward and let the promises the polling code is waiting on settle. */
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("studio status rules", () => {
  it("comes only from the last successful check", () => {
    expect(deriveStudioStatus(null, 0, false)).toBe("loading");
    expect(deriveStudioStatus(view(), 0, false)).toBe("current");
    expect(deriveStudioStatus(view({ newer_revision_pending: true, newer_revision_number: 2 }), 0, false)).toBe("newer_pending");
    expect(deriveStudioStatus(view({ status: "not_approved", version: null, items: [] }), 0, false)).toBe("not_approved");
    expect(deriveStudioStatus(null, 0, true)).toBe("not_found");
  });

  it("is 'cannot confirm' after two failed checks in a row, whatever was last shown", () => {
    expect(STUDIO_FAILURES_BEFORE_UNCONFIRMED).toBe(2);
    expect(deriveStudioStatus(view(), 1, false)).toBe("current"); // one failure is not enough
    expect(deriveStudioStatus(view(), 2, false)).toBe("cannot_confirm");
    expect(deriveStudioStatus(null, 2, false)).toBe("cannot_confirm"); // nothing ever confirmed
    expect(deriveStudioStatus(view({ newer_revision_pending: true }), 3, false)).toBe("cannot_confirm");
  });

  it("polls every 10 seconds", () => {
    expect(STUDIO_POLL_MS).toBe(10_000);
    expect(STUDIO_TIMEOUT_MS).toBeLessThan(STUDIO_POLL_MS); // checks never overlap
  });
});

describe("useStudioStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    api.getStudio.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("checks straight away, then every ten seconds, and reports the server's answer", async () => {
    api.getStudio.mockResolvedValue(view());
    const { result } = renderHook(() => useStudioStatus("b1"));
    expect(result.current.status).toBe("loading");
    await advance(0);
    expect(result.current.status).toBe("current");
    expect(result.current.view?.version).toBe(1);
    expect(result.current.lastConfirmedAt).toBe("2099-01-01T15:59:30Z"); // the server's clock, not the browser's
    expect(api.getStudio).toHaveBeenCalledTimes(1);
    expect(api.getStudio).toHaveBeenCalledWith("b1", expect.any(AbortSignal));
    await advance(10_000);
    expect(api.getStudio).toHaveBeenCalledTimes(2);
    await advance(30_000);
    expect(api.getStudio).toHaveBeenCalledTimes(5);
  });

  it("moves to 'newer version awaiting approval' while still showing the approved one, then to the new version", async () => {
    api.getStudio.mockResolvedValue(view());
    const { result } = renderHook(() => useStudioStatus("b1"));
    await advance(0);
    expect(result.current.status).toBe("current");

    api.getStudio.mockResolvedValue(view({ newer_revision_pending: true, newer_revision_number: 2 }));
    await advance(10_000);
    expect(result.current.status).toBe("newer_pending");
    expect(result.current.view?.version).toBe(1); // the approved version is still what is shown

    api.getStudio.mockResolvedValue(view({ version: 2, newer_revision_pending: false, newer_revision_number: null, server_time: "2099-01-01T16:00:10Z" }));
    await advance(10_000);
    expect(result.current.status).toBe("current");
    expect(result.current.view?.version).toBe(2);
    expect(result.current.lastConfirmedAt).toBe("2099-01-01T16:00:10Z");
  });

  it("says it cannot confirm after two failed checks, keeps the last confirmed view, and recovers on the next success", async () => {
    api.getStudio.mockResolvedValue(view());
    const { result } = renderHook(() => useStudioStatus("b1"));
    await advance(0);
    expect(result.current.status).toBe("current");

    api.getStudio.mockRejectedValue(new ApiError("Could not reach the API.", null));
    await advance(10_000);
    expect(result.current.status).toBe("current"); // one missed check is not yet a verdict
    expect(result.current.failures).toBe(1);
    await advance(10_000);
    expect(result.current.status).toBe("cannot_confirm");
    expect(result.current.failures).toBe(2);
    expect(result.current.view?.version).toBe(1); // the script is still there for the reader...
    expect(result.current.lastConfirmedAt).toBe("2099-01-01T15:59:30Z"); // ...with the time it was last confirmed

    api.getStudio.mockResolvedValue(view({ version: 3 }));
    await advance(10_000);
    expect(result.current.status).toBe("current");
    expect(result.current.failures).toBe(0);
    expect(result.current.view?.version).toBe(3);
  });

  it("treats a server that hangs as a failure, not as silence", async () => {
    api.getStudio.mockImplementation(
      (_id: string, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
        }),
    );
    const { result } = renderHook(() => useStudioStatus("b1"));
    await advance(STUDIO_TIMEOUT_MS + 1); // first check times out
    expect(result.current.failures).toBe(1);
    await advance(STUDIO_POLL_MS); // second check times out
    await advance(STUDIO_TIMEOUT_MS);
    expect(result.current.failures).toBeGreaterThanOrEqual(2);
    expect(result.current.status).toBe("cannot_confirm");
  });

  it("is 'cannot confirm' when it has never heard from the server", async () => {
    api.getStudio.mockRejectedValue(new Error("down"));
    const { result } = renderHook(() => useStudioStatus("b1"));
    await advance(0);
    expect(result.current.status).toBe("loading");
    await advance(10_000);
    expect(result.current.status).toBe("cannot_confirm");
    expect(result.current.view).toBeNull();
    expect(result.current.lastConfirmedAt).toBeNull();
  });

  it("stops asking, and aborts the check in flight, when the screen goes away", async () => {
    let signal: AbortSignal | undefined;
    api.getStudio.mockImplementation((_id: string, s: AbortSignal) => {
      signal = s;
      return new Promise(() => {});
    });
    const { unmount } = renderHook(() => useStudioStatus("b1"));
    await advance(0);
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
    const calls = api.getStudio.mock.calls.length;
    await advance(60_000);
    expect(api.getStudio.mock.calls.length).toBe(calls);
  });

  it("does not count its own abort on unmount as a failed check", async () => {
    api.getStudio.mockImplementation(
      (_id: string, signal: AbortSignal) =>
        new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })))),
    );
    const { result, unmount } = renderHook(() => useStudioStatus("b1"));
    await advance(0);
    unmount();
    await advance(0);
    expect(result.current.failures).toBe(0);
  });

  it("stops retrying a bulletin that does not exist", async () => {
    api.getStudio.mockRejectedValue(new ApiError("No such bulletin.", 404));
    const { result } = renderHook(() => useStudioStatus("missing"));
    await advance(0);
    expect(result.current.status).toBe("not_found");
    expect(result.current.failures).toBe(0);
  });

  it("starts again from scratch for a different bulletin", async () => {
    api.getStudio.mockResolvedValue(view());
    const { result, rerender } = renderHook(({ id }) => useStudioStatus(id), { initialProps: { id: "b1" } });
    await advance(0);
    api.getStudio.mockResolvedValue(view({ bulletin_id: "b2", name: "Noon News" }));
    rerender({ id: "b2" });
    await advance(0);
    expect(api.getStudio).toHaveBeenLastCalledWith("b2", expect.any(AbortSignal));
    expect(result.current.view?.name).toBe("Noon News");
  });
});

/* ------------------------------------------------------------------ the screen */

describe("Studio screen", () => {
  beforeEach(() => {
    api.getStudio.mockReset();
  });
  const renderWith = async (answer: StudioView | Error, polls = 1) => {
    if (answer instanceof Error) api.getStudio.mockRejectedValue(answer);
    else api.getStudio.mockResolvedValue(answer);
    vi.useFakeTimers();
    try {
      render(<StudioScreen id="b1" />);
      for (let i = 0; i < polls; i++) await advance(i === 0 ? 0 : 10_000);
    } finally {
      vi.useRealTimers();
    }
  };

  it("shows the current approved version, who approved it and when the server last confirmed it", async () => {
    await renderWith(view());
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Current · Version 1");
    expect(banner).toHaveTextContent("by Esther Producer");
    expect(banner).toHaveTextContent(/Confirmed with the server at \d\d:\d\d:\d\d/);
    expect(screen.getByRole("heading", { level: 1, name: "6pm News" })).toBeInTheDocument();
  });

  it("shows each story's script in order, with its clip note and the running time", async () => {
    await renderWith(view());
    const order = screen.getByRole("list", { name: "Running order" });
    const items = within(order).getAllByRole("listitem");
    expect(within(items[0]).getByRole("heading", { name: /Council approves budget/ })).toBeInTheDocument();
    expect(within(items[0]).getByText("The council approved its budget on Tuesday.")).toBeInTheDocument();
    expect(within(items[1]).getByText("Note: Play clip 3 after the intro")).toBeInTheDocument();
    expect(within(items[1]).getByText("1:15 · clip")).toBeInTheDocument();
    expect(screen.getByText(/Running time 1:45 of 5:00 · 3:15 under target/)).toBeInTheDocument();
  });

  it("says a newer version is awaiting approval while it keeps showing the approved one", async () => {
    await renderWith(view({ newer_revision_pending: true, newer_revision_number: 2 }));
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Newer version awaiting approval");
    expect(banner).toHaveTextContent("You are reading version 1, the approved one");
    expect(banner).toHaveTextContent("Version 2 has not been approved yet");
    expect(screen.getByText("The council approved its budget on Tuesday.")).toBeInTheDocument(); // still readable
  });

  it("says it cannot confirm, loudly, when the server stops answering, and still shows the script", async () => {
    api.getStudio.mockResolvedValueOnce(view());
    api.getStudio.mockRejectedValue(new ApiError("Could not reach the API.", null));
    vi.useFakeTimers();
    try {
      render(<StudioScreen id="b1" />);
      await advance(0);
      expect(screen.getByRole("status")).toHaveTextContent("Current · Version 1");
      await advance(10_000);
      await advance(10_000);
    } finally {
      vi.useRealTimers();
    }
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Cannot confirm");
    expect(alert).toHaveTextContent("2 checks failed in a row");
    expect(alert).toHaveTextContent(/last confirmed at \d\d:\d\d:\d\d and may be out of date/);
    expect(screen.queryByText(/Current · Version/)).not.toBeInTheDocument(); // never claims to be current
    expect(screen.getByText("The council approved its budget on Tuesday.")).toBeInTheDocument(); // the reader still has the text
  });

  it("says nothing has been confirmed when it never reached the server", async () => {
    await renderWith(new Error("down"), 2);
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot confirm");
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing has been confirmed yet");
    expect(screen.queryByRole("list", { name: "Running order" })).not.toBeInTheDocument();
  });

  it("serves no script for a bulletin that has no approved version", async () => {
    await renderWith(view({ status: "not_approved", version: null, items: [], total_seconds: 0, approved_at: null, approved_by: null, newer_revision_pending: true, newer_revision_number: 1 }));
    expect(screen.getByRole("status")).toHaveTextContent("No approved version yet");
    expect(screen.getByRole("status")).toHaveTextContent("Version 1 is waiting for approval");
    expect(screen.queryByRole("list", { name: "Running order" })).not.toBeInTheDocument();
  });

  it("is read-only: nothing on it can change the bulletin", async () => {
    await renderWith(view());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("explains a bulletin that does not exist", async () => {
    await renderWith(new ApiError("No such bulletin.", 404));
    expect(screen.getByText(/Back to the Studio/)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ the index */

describe("Studio index", () => {
  const summary = (o: Partial<BulletinSummary> = {}): BulletinSummary => ({
    id: "b1",
    name: "6pm News",
    scheduled_for: "2099-01-01T16:00:00Z",
    target_seconds: 300,
    approved_revision_number: 2,
    approved_at: "2099-01-01T14:00:00Z",
    approved_total_seconds: 290,
    latest_revision_number: 2,
    latest_revision_state: "approved",
    aired_at: null,
    created_by: { id: "u", display_name: "Esther" },
    created_at: "2026-11-12T08:00:00Z",
    ...o,
  });

  it("lists bulletins soonest first, marks the next one up and links to each studio screen", async () => {
    api.listBulletins.mockResolvedValue({
      items: [summary({ id: "b0", name: "Noon News", aired_at: "2099-01-01T12:00:00Z" }), summary(), summary({ id: "b2", name: "Late News", approved_revision_number: null, approved_at: null })],
      total: 3,
      page: 1,
      page_size: 50,
    });
    render(<StudioIndex />);
    const list = await screen.findByRole("list", { name: "Bulletins to read" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Broadcast")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Next up")).toBeInTheDocument(); // the first one not yet aired
    expect(within(rows[1]).getByText(/Version 2 approved/)).toBeInTheDocument();
    expect(within(rows[2]).getByText("Not approved yet")).toBeInTheDocument();
    expect(within(rows[1]).getByRole("link", { name: "Open in studio" })).toHaveAttribute("href", "/studio/b1");
    expect(api.listBulletins).toHaveBeenCalledWith(expect.objectContaining({ order: "asc", pageSize: 50, scheduledFrom: expect.any(String) }));
  });

  it("says when there is nothing to read", async () => {
    api.listBulletins.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    render(<StudioIndex />);
    expect(await screen.findByText("No bulletins to read")).toBeInTheDocument();
  });

  it("shows API errors instead of an empty list", async () => {
    api.listBulletins.mockRejectedValue(new Error("The API returned 500."));
    render(<StudioIndex />);
    expect(await screen.findByText(/500/)).toBeInTheDocument();
  });
});
