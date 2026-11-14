import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  defaultRevision,
  moveRow,
  rowFromStory,
  rowSeconds,
  rowsFromRevision,
  timeVersusTarget,
  toDrafts,
  totalSeconds,
} from "@/lib/newsroom/bulletin";
import type { BulletinDetail, BulletinItem, BulletinRevision, BulletinSummary, RevisionState, StorySummary } from "@/lib/newsroom/types";
import type { SessionUser, UserRole } from "@/types";
import { BulletinBuilder } from "./bulletin-builder";
import { BulletinList, localInputToIso } from "./bulletin-list";

const api = vi.hoisted(() => ({
  listBulletins: vi.fn(),
  getBulletin: vi.fn(),
  createBulletin: vi.fn(),
  createRevision: vi.fn(),
  saveBulletinItems: vi.fn(),
  submitRevision: vi.fn(),
  approveRevision: vi.fn(),
  rejectRevision: vi.fn(),
  broadcastBulletin: vi.fn(),
  listStories: vi.fn(),
}));
const nav = vi.hoisted(() => ({ push: vi.fn() }));
const auth = vi.hoisted(() => ({ user: null as SessionUser | null }));

vi.mock("@/lib/api/newsroom", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/bulletins",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/hooks/use-demo-session", () => ({
  useSession: () => ({ user: auth.user, signedOut: false, loading: false, signIn: vi.fn(), signOut: vi.fn() }),
}));

const signIn = (role: UserRole, id: string) => {
  auth.user = { id, name: id, email: `${id}@example.test`, role, title: role, isDemo: false };
};
const asProducer = () => signIn("editor", "u-ep");
const asReporter = () => signIn("reporter", "u-rep");

const ep = { id: "u-ep", display_name: "Esther Producer" };

const item = (n: number, o: Partial<BulletinItem> = {}): BulletinItem => ({
  position: n,
  story: { id: `st${n}`, title: `Story ${n}`, stage: "approved" },
  script: { id: `sc${n}`, version_number: 1, headline: `Headline ${n}`, estimated_seconds: 30 },
  script_approved: true,
  newer_script_version: null,
  duration_seconds: 30,
  duration_overridden: false,
  note: null,
  ...o,
});

const rev = (n: number, state: RevisionState, items: BulletinItem[] = [item(1), item(2)], o: Partial<BulletinRevision> = {}): BulletinRevision => ({
  id: `rev${n}`,
  revision_number: n,
  state,
  items,
  total_seconds: items.reduce((s, i) => s + i.duration_seconds, 0),
  created_by: ep,
  created_at: "2026-11-12T08:00:00Z",
  submitted_by: state === "draft" ? null : ep,
  submitted_at: state === "draft" ? null : "2026-11-12T08:30:00Z",
  approved_by: state === "approved" || state === "superseded" ? ep : null,
  approved_at: state === "approved" || state === "superseded" ? "2026-11-12T09:00:00Z" : null,
  aired_by: null,
  aired_at: null,
  decisions: [],
  ...o,
});

const bulletin = (revisions: BulletinRevision[], o: Partial<BulletinDetail> = {}): BulletinDetail => {
  const approved = revisions.find((r) => r.state === "approved");
  const latest = revisions[revisions.length - 1];
  return {
    id: "b1",
    name: "6pm News",
    scheduled_for: "2099-01-01T16:00:00Z",
    target_seconds: 300,
    approved_revision_number: approved?.revision_number ?? null,
    approved_at: approved?.approved_at ?? null,
    approved_total_seconds: approved?.total_seconds ?? null,
    latest_revision_number: latest.revision_number,
    latest_revision_state: latest.state,
    aired_at: approved?.aired_at ?? null,
    created_by: ep,
    created_at: "2026-11-12T08:00:00Z",
    revisions,
    ...o,
  };
};

const story = (n: number, o: Partial<StorySummary> = {}): StorySummary => ({
  id: `cand${n}`,
  title: `Candidate ${n}`,
  stage: "approved",
  assignee: { id: "u-rep", display_name: "Rudo" },
  deadline_at: null,
  source_item_id: null,
  article_headline: null,
  verified: true,
  latest_script_version: 1,
  latest_script_seconds: 45,
  approved_script_version: 1,
  follows_story_id: null,
  created_at: "2026-11-10T08:00:00Z",
  updated_at: "2026-11-10T09:00:00Z",
  ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  asProducer();
  api.listStories.mockResolvedValue({ items: [story(1), story(2, { stage: "in_review", approved_script_version: null })], total: 2, page: 1, page_size: 100 });
  api.getBulletin.mockResolvedValue(bulletin([rev(1, "draft")]));
});

/* ------------------------------------------------------------------ pure builder logic */

describe("builder logic", () => {
  it("moves a row up or down and ignores moves off either end", () => {
    expect(moveRow(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveRow(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
    const same = ["a", "b"];
    expect(moveRow(same, 0, -1)).toBe(same);
    expect(moveRow(same, 1, 1)).toBe(same);
  });

  it("times the running order against the target in words and numbers", () => {
    expect(timeVersusTarget(270, 300)).toEqual({ state: "under", difference: 30, label: "0:30 under target", percent: 90 });
    expect(timeVersusTarget(315, 300)).toEqual({ state: "over", difference: 15, label: "0:15 over target", percent: 100 });
    expect(timeVersusTarget(300, 300)).toMatchObject({ state: "on", label: "On target", percent: 100 });
    expect(timeVersusTarget(0, 300).percent).toBe(0);
  });

  it("uses a clip's length instead of the reading-time estimate", () => {
    const rows = rowsFromRevision(rev(1, "draft", [item(1), item(2, { duration_seconds: 90, duration_overridden: true })]));
    expect(rows.map(rowSeconds)).toEqual([30, 90]);
    expect(totalSeconds(rows)).toBe(120);
    expect(rows[1].overrideSeconds).toBe(90);
    expect(rows[0].overrideSeconds).toBeNull();
  });

  it("turns rows back into what the API expects, keeping the pinned script", () => {
    const rows = rowsFromRevision(rev(1, "draft", [item(1, { note: "Play clip 3" })]));
    expect(toDrafts(rows)).toEqual([{ storyId: "st1", scriptId: "sc1", durationOverrideSeconds: null, note: "Play clip 3" }]);
  });

  it("lets the server pin the script of a story added in the browser", () => {
    const row = rowFromStory(story(1));
    expect(row).toMatchObject({ storyId: "cand1", scriptId: null, saved: false, approved: true, seconds: 45 });
    expect(rowFromStory(story(2, { approved_script_version: null })).approved).toBe(false);
  });

  it("opens on the revision being worked on, else the live one, else the newest", () => {
    const revisions = [rev(1, "superseded"), rev(2, "approved"), rev(3, "pending_approval")];
    expect(defaultRevision(revisions, 2).revision_number).toBe(3);
    expect(defaultRevision([rev(1, "superseded"), rev(2, "approved")], 2).revision_number).toBe(2);
    expect(defaultRevision([rev(1, "rejected")], null).revision_number).toBe(1);
  });
});

/* ------------------------------------------------------------------ builder */

describe("Bulletin builder", () => {
  it("shows the running order, each story's script version and approval, and the time against the target", async () => {
    render(<BulletinBuilder id="b1" />);
    const order = await screen.findByRole("list", { name: "Running order" });
    expect(within(order).getByText("Story 1")).toBeInTheDocument();
    expect(within(order).getAllByText("Script approved")).toHaveLength(2);
    expect(within(order).getAllByText("Script version 1")).toHaveLength(2);
    expect(screen.getByText("1:00")).toBeInTheDocument();
    expect(screen.getByText("of 5:00")).toBeInTheDocument();
    expect(screen.getByText("4:00 under target")).toBeInTheDocument();
    const meter = screen.getByRole("meter", { name: "Running time against the target" });
    expect(meter).toHaveAttribute("aria-valuenow", "60");
    expect(meter).toHaveAttribute("aria-valuemax", "300");
  });

  it("says when the bulletin runs over", async () => {
    api.getBulletin.mockResolvedValue(bulletin([rev(1, "draft", [item(1, { duration_seconds: 330, duration_overridden: true })])]));
    render(<BulletinBuilder id="b1" />);
    expect(await screen.findByText("0:30 over target")).toBeInTheDocument();
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuetext", expect.stringContaining("0:30 over target"));
  });

  it("adds a story from the list, saves the order and lets the server pin the script", async () => {
    api.saveBulletinItems.mockResolvedValue(bulletin([rev(1, "draft", [item(1), item(2), item(3)])]));
    render(<BulletinBuilder id="b1" />);
    await screen.findByRole("list", { name: "Running order" });
    expect(screen.getByRole("button", { name: "Save running order" })).toBeDisabled(); // nothing changed
    await userEvent.click(await screen.findByRole("button", { name: "Add Candidate 1" }));
    expect(screen.getByText("Not saved yet")).toBeInTheDocument();
    expect(screen.getByText("1:45")).toBeInTheDocument(); // 30 + 30 + 45
    expect(screen.queryByRole("button", { name: "Add Candidate 1" })).not.toBeInTheDocument(); // already in
    await userEvent.click(screen.getByRole("button", { name: "Save running order" }));
    await waitFor(() =>
      expect(api.saveBulletinItems).toHaveBeenCalledWith("b1", 1, [
        { storyId: "st1", scriptId: "sc1", durationOverrideSeconds: null, note: "" },
        { storyId: "st2", scriptId: "sc2", durationOverrideSeconds: null, note: "" },
        { storyId: "cand1", scriptId: null, durationOverrideSeconds: null, note: "" },
      ]),
    );
  });

  it("reorders, removes and times a clip", async () => {
    api.saveBulletinItems.mockResolvedValue(bulletin([rev(1, "draft")]));
    render(<BulletinBuilder id="b1" />);
    await screen.findByRole("list", { name: "Running order" });
    await userEvent.click(screen.getByRole("button", { name: "Move Story 2 up" }));
    const titles = () => within(screen.getByRole("list", { name: "Running order" })).getAllByRole("link").map((a) => a.textContent);
    expect(titles()).toEqual(["Story 2", "Story 1"]);
    expect(screen.getByRole("button", { name: "Move Story 2 up" })).toBeDisabled(); // first row
    fireEvent.change(screen.getByLabelText("Clip length in seconds for Story 1"), { target: { value: "90" } });
    expect(screen.getByText("2:00")).toBeInTheDocument(); // 30 + 90
    expect(screen.getByLabelText("Duration 1:30")).toHaveTextContent("clip");
    fireEvent.change(screen.getByLabelText("Note for Story 1"), { target: { value: "Play clip 3" } });
    await userEvent.click(screen.getByRole("button", { name: "Remove Story 2" }));
    expect(titles()).toEqual(["Story 1"]);
    await userEvent.click(screen.getByRole("button", { name: "Save running order" }));
    await waitFor(() =>
      expect(api.saveBulletinItems).toHaveBeenCalledWith("b1", 1, [{ storyId: "st1", scriptId: "sc1", durationOverrideSeconds: 90, note: "Play clip 3" }]),
    );
  });

  it("will not submit unsaved changes, an empty bulletin or one with an unapproved script, and says why", async () => {
    api.getBulletin.mockResolvedValue(bulletin([rev(1, "draft", [item(1), item(2, { script_approved: false })])]));
    const { unmount } = render(<BulletinBuilder id="b1" />);
    await screen.findByRole("list", { name: "Running order" });
    expect(screen.getByRole("button", { name: /Submit for approval/ })).toBeDisabled();
    expect(screen.getByText(/One story has a script that is not approved yet/)).toBeInTheDocument();
    unmount();

    api.getBulletin.mockResolvedValue(bulletin([rev(1, "draft", [])]));
    render(<BulletinBuilder id="b1" />);
    expect(await screen.findByText("Add at least one story.")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Add Candidate 1" }));
    expect(screen.getByText("Save the running order before submitting.")).toBeInTheDocument();
  });

  it("submits a saved bulletin whose scripts are all approved", async () => {
    api.submitRevision.mockResolvedValue(bulletin([rev(1, "pending_approval")]));
    render(<BulletinBuilder id="b1" />);
    const submit = await screen.findByRole("button", { name: /Submit for approval/ });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => expect(api.submitRevision).toHaveBeenCalledWith("b1", 1));
  });

  it("flags a story that has been rewritten and can re-pin it to the current approved version", async () => {
    api.getBulletin.mockResolvedValue(bulletin([rev(1, "draft", [item(1, { newer_script_version: 2 })])]));
    api.saveBulletinItems.mockResolvedValue(bulletin([rev(1, "draft")]));
    render(<BulletinBuilder id="b1" />);
    expect(await screen.findByText("Newer script (version 2) exists")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use current approved version" }));
    expect(screen.queryByText(/Newer script/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save running order" }));
    await waitFor(() => expect(api.saveBulletinItems).toHaveBeenCalledWith("b1", 1, [{ storyId: "st1", scriptId: null, durationOverrideSeconds: null, note: "" }]));
  });

  describe("approval", () => {
    const pending = () => bulletin([rev(1, "pending_approval")]);

    it("approves a submitted revision with an optional comment", async () => {
      api.getBulletin.mockResolvedValue(pending());
      api.approveRevision.mockResolvedValue(bulletin([rev(1, "approved")]));
      render(<BulletinBuilder id="b1" />);
      await screen.findByText(/Revision 1 is waiting for you/);
      await userEvent.type(screen.getByLabelText("Approval comment"), "Good order");
      await userEvent.click(screen.getByRole("button", { name: /Approve/ }));
      await waitFor(() => expect(api.approveRevision).toHaveBeenCalledWith("b1", 1, "Good order"));
    });

    it("needs a comment to reject", async () => {
      api.getBulletin.mockResolvedValue(pending());
      api.rejectRevision.mockResolvedValue(bulletin([rev(1, "rejected")]));
      render(<BulletinBuilder id="b1" />);
      await screen.findByLabelText("Approval comment");
      expect(screen.getByRole("button", { name: /Reject/ })).toBeDisabled();
      await userEvent.type(screen.getByLabelText("Approval comment"), "Too long");
      await userEvent.click(screen.getByRole("button", { name: /Reject/ }));
      await waitFor(() => expect(api.rejectRevision).toHaveBeenCalledWith("b1", 1, "Too long"));
    });

    it("warns, but allows, approving a revision the same person submitted", async () => {
      api.getBulletin.mockResolvedValue(pending());
      render(<BulletinBuilder id="b1" />);
      expect(await screen.findByText(/recorded as self-approved/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Approve/ })).toBeEnabled();
    });

    it("keeps the old revision live while the new one waits, and says so", async () => {
      api.getBulletin.mockResolvedValue(bulletin([rev(1, "approved"), rev(2, "pending_approval")]));
      render(<BulletinBuilder id="b1" />);
      expect(await screen.findByText("Live: revision 1")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Revision 1 · live" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Revision 2", pressed: true })).toBeInTheDocument(); // opens on the one being worked on
      expect(screen.getByText(/supersedes the current one/)).toBeInTheDocument();
      // looking at the live revision shows it read-only
      await userEvent.click(screen.getByRole("button", { name: "Revision 1 · live" }));
      expect(screen.getByText(/This is what is approved and live/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    });

    it("marks self-approved decisions in the history", async () => {
      api.getBulletin.mockResolvedValue(
        bulletin([rev(1, "approved", [item(1)], { decisions: [{ decision: "approved", comment: "Fine", self_approved: true, reviewer: ep, decided_at: "2026-11-12T09:00:00Z" }] })]),
      );
      render(<BulletinBuilder id="b1" />);
      expect(await screen.findByText("Self-approved")).toBeInTheDocument();
      expect(screen.getByText(/Approved by Esther Producer/)).toBeInTheDocument();
    });
  });

  describe("a live bulletin", () => {
    const live = (o: Partial<BulletinRevision> = {}) => bulletin([rev(1, "approved", [item(1), item(2)], o)]);

    it("cannot be edited in place; changing it starts a new revision", async () => {
      api.getBulletin.mockResolvedValue(live());
      api.createRevision.mockResolvedValue(bulletin([rev(1, "approved"), rev(2, "draft")]));
      render(<BulletinBuilder id="b1" />);
      await screen.findByText(/This is what is approved and live/);
      for (const name of [/Save running order/, /Submit for approval/, /Add Candidate/, /Remove Story/]) {
        expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      }
      await userEvent.click(screen.getByRole("button", { name: "Change this bulletin" }));
      await waitFor(() => expect(api.createRevision).toHaveBeenCalledWith("b1"));
    });

    it("offers no second revision while one is already open", async () => {
      api.getBulletin.mockResolvedValue(bulletin([rev(1, "approved"), rev(2, "draft")]));
      render(<BulletinBuilder id="b1" />);
      await screen.findByText("Live: revision 1");
      expect(screen.queryByRole("button", { name: "Change this bulletin" })).not.toBeInTheDocument();
    });

    it("is marked as broadcast once, then the button goes away", async () => {
      api.getBulletin.mockResolvedValue(live());
      api.broadcastBulletin.mockResolvedValue(live({ aired_at: "2026-11-12T16:00:00Z", aired_by: ep }));
      const { unmount } = render(<BulletinBuilder id="b1" />);
      await userEvent.click(await screen.findByRole("button", { name: /Mark as broadcast/ }));
      await waitFor(() => expect(api.broadcastBulletin).toHaveBeenCalledWith("b1"));
      unmount();

      api.getBulletin.mockResolvedValue(live({ aired_at: "2026-11-12T16:00:00Z", aired_by: ep }));
      render(<BulletinBuilder id="b1" />);
      await screen.findByText("Live: revision 1");
      expect(screen.getAllByText("Broadcast").length).toBeGreaterThan(0);
      expect(screen.queryByRole("button", { name: /Mark as broadcast/ })).not.toBeInTheDocument();
    });

    it("shows a clip's note to everyone", async () => {
      api.getBulletin.mockResolvedValue(bulletin([rev(1, "approved", [item(1, { note: "Play clip 3" })])]));
      render(<BulletinBuilder id="b1" />);
      expect(await screen.findByText("Note: Play clip 3")).toBeInTheDocument();
    });
  });

  it("is read-only for a reporter", async () => {
    asReporter();
    api.getBulletin.mockResolvedValue(bulletin([rev(1, "approved"), rev(2, "pending_approval")]));
    render(<BulletinBuilder id="b1" />);
    await screen.findByText("Live: revision 1");
    for (const name of [/Approve/, /Reject/, /Save running order/, /Submit for approval/, /Change this bulletin/, /Mark as broadcast/, /Add /]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByLabelText("Approval comment")).not.toBeInTheDocument();
    expect(api.listStories).not.toHaveBeenCalled(); // no candidate list for someone who cannot add
  });

  it("explains a missing bulletin", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.getBulletin.mockRejectedValue(new ApiError("No such bulletin.", 404));
    render(<BulletinBuilder id="missing" />);
    expect(await screen.findByText(/Back to Bulletins/)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ list */

describe("Bulletin list", () => {
  const summary = (o: Partial<BulletinSummary> = {}): BulletinSummary => ({
    id: "b1",
    name: "6pm News",
    scheduled_for: "2099-01-01T16:00:00Z",
    target_seconds: 300,
    approved_revision_number: null,
    approved_at: null,
    approved_total_seconds: null,
    latest_revision_number: 1,
    latest_revision_state: "draft",
    aired_at: null,
    created_by: ep,
    created_at: "2026-11-12T08:00:00Z",
    ...o,
  });

  beforeEach(() => {
    api.listBulletins.mockResolvedValue({
      items: [
        summary(),
        summary({ id: "b2", name: "Noon News", approved_revision_number: 2, approved_total_seconds: 290, latest_revision_number: 3, latest_revision_state: "pending_approval", aired_at: "2026-11-12T12:00:00Z" }),
      ],
      total: 2,
      page: 1,
      page_size: 50,
    });
  });

  it("lists bulletins with their live revision, what is waiting and whether they aired", async () => {
    render(<BulletinList />);
    const list = await screen.findByRole("list", { name: "Bulletins" });
    expect(within(list).getByRole("link", { name: "6pm News" })).toHaveAttribute("href", "/bulletins/b1");
    const noon = within(list).getByRole("link", { name: "Noon News" }).closest("li")!;
    expect(within(noon).getByText("Live: revision 2")).toBeInTheDocument();
    expect(within(noon).getByText(/runs 4:50/)).toBeInTheDocument();
    expect(within(noon).getByText("Awaiting approval")).toBeInTheDocument();
    expect(within(noon).getByText("Broadcast")).toBeInTheDocument();
    expect(within(list.querySelector("li")!).getByText("Draft")).toBeInTheDocument();
  });

  it("lets the Executive Producer create a bulletin and opens the builder", async () => {
    api.createBulletin.mockResolvedValue(bulletin([rev(1, "draft", [])], { id: "new-b" }));
    render(<BulletinList />);
    await screen.findByRole("list", { name: "Bulletins" });
    const create = screen.getByRole("button", { name: "Create" });
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Bulletin name"), "  Breakfast news ");
    fireEvent.change(screen.getByLabelText("Air time"), { target: { value: "2099-03-01T07:00" } });
    fireEvent.change(screen.getByLabelText("Target length in minutes"), { target: { value: "2.5" } });
    expect(create).toBeEnabled();
    await userEvent.click(create);
    await waitFor(() =>
      expect(api.createBulletin).toHaveBeenCalledWith({ name: "Breakfast news", scheduledFor: localInputToIso("2099-03-01T07:00"), targetSeconds: 150 }),
    );
    expect(nav.push).toHaveBeenCalledWith("/bulletins/new-b");
  });

  it("does not offer creation to a reporter", async () => {
    asReporter();
    render(<BulletinList />);
    await screen.findByRole("list", { name: "Bulletins" });
    expect(screen.queryByLabelText("Bulletin name")).not.toBeInTheDocument();
    expect(screen.getByText(/The Executive Producer builds and approves them/)).toBeInTheDocument();
  });

  it("says when there are none and shows API errors instead of an empty list", async () => {
    api.listBulletins.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    const { unmount } = render(<BulletinList />);
    expect(await screen.findByText("No bulletins yet")).toBeInTheDocument();
    unmount();
    api.listBulletins.mockRejectedValue(new Error("The API returned 500."));
    render(<BulletinList />);
    expect(await screen.findByText(/500/)).toBeInTheDocument();
  });

  it("converts a local date-time to an instant and rejects nonsense", () => {
    expect(localInputToIso("2099-03-01T07:00")).toBe(new Date("2099-03-01T07:00").toISOString());
    expect(localInputToIso("not a date")).toBeNull();
    expect(localInputToIso("")).toBeNull();
  });
});
