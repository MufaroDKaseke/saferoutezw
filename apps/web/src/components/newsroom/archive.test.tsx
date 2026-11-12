import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArchiveBulletin, ArchiveBulletinDetail, ArchiveStory, ArchiveStoryDetail } from "@/lib/newsroom/types";
import type { SessionUser, UserRole } from "@/types";
import { ArchiveStoryView } from "./archive-story";
import { ArchiveView, dayEndIso, dayStartIso } from "./archive-view";

const api = vi.hoisted(() => ({
  searchArchive: vi.fn(),
  searchArchivedBulletins: vi.fn(),
  getArchivedStory: vi.fn(),
  getArchivedBulletin: vi.fn(),
  takeStory: vi.fn(),
}));
const nav = vi.hoisted(() => ({ push: vi.fn() }));
const auth = vi.hoisted(() => ({ user: null as SessionUser | null }));

vi.mock("@/lib/api/newsroom", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/archive",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/hooks/use-demo-session", () => ({
  useSession: () => ({ user: auth.user, signedOut: false, loading: false, signIn: vi.fn(), signOut: vi.fn() }),
}));

const signIn = (role: UserRole) => {
  auth.user = { id: `u-${role}`, name: role, email: `${role}@example.test`, role, title: role, isDemo: false };
};

const rudo = { id: "u-rep", display_name: "Rudo Reporter" };
const esther = { id: "u-ep", display_name: "Esther Producer" };
const ref = { id: "b1", name: "6pm News", revision_number: 1, aired_at: "2026-11-12T16:00:00Z" };

const story = (o: Partial<ArchiveStory> = {}): ArchiveStory => ({
  id: "s1",
  title: "Council budget",
  headline: "Council approves budget",
  excerpt: "The council approved its 2027 budget on Tuesday.",
  category: "politics_governance",
  category_label: "Politics & Governance",
  aired_at: "2026-11-12T16:00:00Z",
  last_aired_at: "2026-11-12T16:00:00Z",
  bulletins: [ref],
  reporter: rudo,
  follows: null,
  follow_up_count: 0,
  publisher: "The Herald",
  source_url: "https://herald.example/budget",
  ...o,
});

const detail = (o: Partial<ArchiveStoryDetail> = {}): ArchiveStoryDetail => ({
  ...story(),
  source_item_id: "a1",
  scripts: [
    { version_number: 1, headline: "Council approves budget", body: "The aired text of version one.", estimated_seconds: 30, origin: "ai_draft", created_by: rudo, created_at: "2026-11-12T09:00:00Z", aired_in: [ref] },
  ],
  versions: [
    { version_number: 1, origin: "ai_draft", created_by: rudo, created_at: "2026-11-12T09:00:00Z", approved: true, aired: true },
    { version_number: 2, origin: "human", created_by: rudo, created_at: "2026-11-12T10:00:00Z", approved: false, aired: false },
  ],
  reviews: [{ script_version: 1, decision: "approved", comment: "Fine", self_approved: true, reviewer: esther, reviewed_at: "2026-11-12T09:30:00Z" }],
  followed_by: [],
  ...o,
});

const bulletin = (o: Partial<ArchiveBulletin> = {}): ArchiveBulletin => ({
  id: "b1",
  name: "6pm News",
  scheduled_for: "2026-11-12T16:00:00Z",
  revision_number: 1,
  aired_at: "2026-11-12T16:00:00Z",
  aired_by: esther,
  total_seconds: 95,
  story_count: 2,
  ...o,
});

const page = <T,>(items: T[], total = items.length) => ({ items, total, page: 1, page_size: 15 });

beforeEach(() => {
  vi.clearAllMocks();
  signIn("reporter");
  api.searchArchive.mockResolvedValue(page([story()]));
  api.searchArchivedBulletins.mockResolvedValue(page([bulletin()]));
  api.getArchivedStory.mockResolvedValue(detail());
});

describe("archive date filters", () => {
  it("covers the whole of the chosen days in the browser's clock", () => {
    expect(dayStartIso("2026-11-12")).toBe(new Date("2026-11-12T00:00:00").toISOString());
    expect(dayEndIso("2026-11-12")).toBe(new Date("2026-11-12T23:59:59.999").toISOString());
    expect(new Date(dayEndIso("2026-11-12")!).getTime()).toBeGreaterThan(new Date(dayStartIso("2026-11-12")!).getTime());
    expect(dayStartIso("")).toBeUndefined();
    expect(dayEndIso("nonsense")).toBeUndefined();
  });
});

describe("Archive", () => {
  it("lists aired stories with the headline that aired, where and when, who wrote it and a link to the history", async () => {
    render(<ArchiveView />);
    const list = await screen.findByRole("list", { name: "Aired stories" });
    const row = within(list).getByRole("link", { name: "Council budget" }).closest("li")!;
    expect(within(row).getByRole("link", { name: "Council budget" })).toHaveAttribute("href", "/archive/stories/s1");
    expect(within(row).getByText("Aired as: Council approves budget")).toBeInTheDocument();
    expect(within(row).getByText("The council approved its 2027 budget on Tuesday.")).toBeInTheDocument();
    expect(within(row).getByText("Politics & Governance")).toBeInTheDocument();
    expect(within(row).getByText("6pm News")).toBeInTheDocument();
    expect(within(row).getByText("Rudo Reporter")).toBeInTheDocument();
    expect(api.searchArchive).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 15 }));
  });

  it("shows follow-up links in both directions", async () => {
    api.searchArchive.mockResolvedValue(
      page([
        story({ id: "s1", follow_up_count: 2 }),
        story({ id: "s2", title: "Council responds", follows: { id: "s1", title: "Council budget", aired_at: "2026-11-12T16:00:00Z" } }),
      ]),
    );
    render(<ArchiveView />);
    await screen.findByRole("list", { name: "Aired stories" });
    expect(screen.getByText("2 follow-ups")).toBeInTheDocument();
    const second = screen.getByRole("link", { name: "Council responds" }).closest("li")!;
    expect(within(second).getByText("Follow-up")).toBeInTheDocument();
    expect(within(second).getByRole("link", { name: "Council budget" })).toHaveAttribute("href", "/archive/stories/s1");
  });

  it("searches through the API once the person stops typing", async () => {
    render(<ArchiveView />);
    await screen.findByRole("list", { name: "Aired stories" });
    await userEvent.type(screen.getByLabelText("Search titles and scripts"), "okapi");
    await waitFor(() => expect(api.searchArchive).toHaveBeenLastCalledWith(expect.objectContaining({ q: "okapi", page: 1 })));
  });

  it("filters by the days aired, covering each whole day", async () => {
    render(<ArchiveView />);
    await screen.findByRole("list", { name: "Aired stories" });
    fireEvent.change(screen.getByLabelText("Aired from"), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("Aired to"), { target: { value: "2026-11-12" } });
    await waitFor(() =>
      expect(api.searchArchive).toHaveBeenLastCalledWith(
        expect.objectContaining({ airedFrom: dayStartIso("2026-11-10"), airedTo: dayEndIso("2026-11-12") }),
      ),
    );
  });

  it("switches to aired bulletins, which have no category filter, and shows what was read in each", async () => {
    api.getArchivedBulletin.mockResolvedValue({
      ...bulletin(),
      target_seconds: 300,
      approved_at: "2026-11-12T15:00:00Z",
      approved_by: esther,
      items: [
        { position: 1, story_id: "s1", story_title: "Council budget", headline: "Council approves budget", body: "The aired text of the first story.", duration_seconds: 30, duration_overridden: false, note: null },
        { position: 2, story_id: "s2", story_title: "Dam", headline: "Dam levels fall", body: "The dam text.", duration_seconds: 65, duration_overridden: true, note: "Play clip 3" },
      ],
    } satisfies ArchiveBulletinDetail);
    render(<ArchiveView />);
    await screen.findByRole("list", { name: "Aired stories" });
    await userEvent.click(screen.getByRole("button", { name: "Bulletins" }));
    const list = await screen.findByRole("list", { name: "Aired bulletins" });
    expect(screen.queryByText("Category")).not.toBeInTheDocument();
    expect(api.searchArchivedBulletins).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 15 }));
    expect(within(list).getByText("1:35", { exact: false })).toBeInTheDocument();
    expect(within(list).getByText(/2 stories/)).toBeInTheDocument();
    expect(api.getArchivedBulletin).not.toHaveBeenCalled(); // loaded only when opened
    await userEvent.click(screen.getByRole("button", { name: "Show running order" }));
    expect(await screen.findByText("The aired text of the first story.")).toBeInTheDocument();
    expect(api.getArchivedBulletin).toHaveBeenCalledWith("b1", 1);
    expect(screen.getByText("Note: Play clip 3")).toBeInTheDocument();
    expect(screen.getByText(/1:05 · clip/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide running order" }));
    expect(screen.queryByText("The aired text of the first story.")).not.toBeInTheDocument();
  });

  it("pages through the results", async () => {
    api.searchArchive.mockResolvedValue({ items: [story()], total: 40, page: 1, page_size: 15 });
    render(<ArchiveView />);
    await screen.findByText(/40 stories · page 1 of 3/);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.searchArchive).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });

  it("says when nothing has aired and shows API errors instead of an empty list", async () => {
    api.searchArchive.mockResolvedValue(page([]));
    const { unmount } = render(<ArchiveView />);
    expect(await screen.findByText("No aired stories match")).toBeInTheDocument();
    unmount();
    api.searchArchive.mockRejectedValue(new Error("The API returned 500."));
    render(<ArchiveView />);
    expect(await screen.findByText(/500/)).toBeInTheDocument();
  });
});

describe("Archived story", () => {
  it("shows the aired script, where it aired and the decisions, and keeps unaired versions to a one-line history", async () => {
    render(<ArchiveStoryView id="s1" />);
    expect(await screen.findByText("The aired text of version one.")).toBeInTheDocument();
    expect(screen.getByText(/6pm News \(revision 1/)).toBeInTheDocument();
    expect(screen.getAllByText("AI draft").length).toBeGreaterThan(0);
    const versions = screen.getByRole("list", { name: "Script versions" });
    const [two, one] = within(versions).getAllByRole("listitem");
    expect(within(two).getByText("Version 2")).toBeInTheDocument();
    expect(within(two).getByText("Not approved")).toBeInTheDocument();
    expect(within(two).queryByText("Aired")).not.toBeInTheDocument();
    expect(within(one).getByText("Approved")).toBeInTheDocument();
    expect(within(one).getByText("Aired")).toBeInTheDocument();
    const decisions = screen.getByRole("list", { name: "Decisions" });
    expect(within(decisions).getByText("Approved version 1")).toBeInTheDocument();
    expect(within(decisions).getByText("Self-approved")).toBeInTheDocument();
    expect(within(decisions).getByText("“Fine”")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Source article" })).toHaveAttribute("href", "/news/a1");
  });

  it("links follow-ups in both directions", async () => {
    api.getArchivedStory.mockResolvedValue(
      detail({
        follows: { id: "s0", title: "Earlier story", aired_at: "2026-11-01T16:00:00Z" },
        followed_by: [{ id: "s2", title: "Later story", aired_at: "2026-11-20T16:00:00Z" }],
      }),
    );
    render(<ArchiveStoryView id="s1" />);
    expect(await screen.findByRole("link", { name: "Earlier story" })).toHaveAttribute("href", "/archive/stories/s0");
    expect(within(screen.getByRole("list", { name: "Follow-ups" })).getByRole("link", { name: "Later story" })).toHaveAttribute("href", "/archive/stories/s2");
  });

  it("says when there are no follow-ups yet", async () => {
    render(<ArchiveStoryView id="s1" />);
    expect(await screen.findByText("No follow-ups have aired yet.")).toBeInTheDocument();
  });

  it("lets a reporter start a follow-up that points back at the story", async () => {
    api.takeStory.mockResolvedValue({ id: "new-story" });
    render(<ArchiveStoryView id="s1" />);
    await userEvent.click(await screen.findByRole("button", { name: /Start a follow-up/ }));
    await waitFor(() => expect(api.takeStory).toHaveBeenCalledWith({ title: "Follow-up: Council budget", followsStoryId: "s1" }));
    expect(nav.push).toHaveBeenCalledWith("/stories/new-story");
  });

  it("does not offer a follow-up to an analyst, who can only read", async () => {
    signIn("analyst");
    render(<ArchiveStoryView id="s1" />);
    await screen.findByText("The aired text of version one.");
    expect(screen.queryByRole("button", { name: /Start a follow-up/ })).not.toBeInTheDocument();
  });

  it("explains a story that is not in the archive", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.getArchivedStory.mockRejectedValue(new ApiError("That story is not in the archive.", 404));
    render(<ArchiveStoryView id="draft" />);
    expect(await screen.findByText(/Back to the Archive/)).toBeInTheDocument();
  });
});
