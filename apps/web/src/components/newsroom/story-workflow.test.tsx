import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BOARD_STAGES } from "@/lib/newsroom/taxonomy";
import type { NewsroomArticleDetail, StoryDetail, StoryLink, StoryScript, StorySummary } from "@/lib/newsroom/types";
import type { SessionUser, UserRole } from "@/types";
import { ArticleStoryCard } from "./article-story-card";
import { StoryBoard } from "./story-board";
import { StoryWorkspace } from "./story-workspace";

const api = vi.hoisted(() => ({
  listStories: vi.fn(),
  getStory: vi.fn(),
  getNewsroomArticle: vi.fn(),
  takeStory: vi.fn(),
  verifyStory: vi.fn(),
  saveScript: vi.fn(),
  draftScript: vi.fn(),
  submitStory: vi.fn(),
  reviewStory: vi.fn(),
  dropStory: vi.fn(),
  listAssignees: vi.fn(),
}));
const nav = vi.hoisted(() => ({ push: vi.fn() }));
const auth = vi.hoisted(() => ({ user: null as SessionUser | null }));

vi.mock("@/lib/api/newsroom", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/stories",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/hooks/use-demo-session", () => ({
  useSession: () => ({ user: auth.user, signedOut: false, loading: false, signIn: vi.fn(), signOut: vi.fn() }),
}));

const signIn = (role: UserRole, id: string, name: string) => {
  auth.user = { id, name, email: `${id}@example.test`, role, title: role, isDemo: false };
};
const asReporter = () => signIn("reporter", "u-rep", "Rudo Reporter");
const asProducer = () => signIn("editor", "u-ep", "Esther Producer");
const asAnalyst = () => signIn("analyst", "u-an", "Ana Analyst");

const rudo = { id: "u-rep", display_name: "Rudo Reporter" };
const thabo = { id: "u-other", display_name: "Thabo Other" };
const esther = { id: "u-ep", display_name: "Esther Producer" };

const summary = (o: Partial<StorySummary> = {}): StorySummary => ({
  id: "s1",
  title: "Council approves budget",
  stage: "drafting",
  assignee: rudo,
  deadline_at: "2099-01-01T10:00:00Z",
  source_item_id: "a1",
  article_headline: "Budget presented",
  verified: true,
  latest_script_version: null,
  latest_script_seconds: null,
  approved_script_version: null,
  follows_story_id: null,
  created_at: "2026-11-10T08:00:00Z",
  updated_at: "2026-11-10T09:00:00Z",
  ...o,
});

const script = (n: number, o: Partial<StoryScript> = {}): StoryScript => ({
  id: `sc${n}`,
  version_number: n,
  headline: `Headline v${n}`,
  body: "The council approved the budget, according to The Herald.",
  estimated_seconds: 30,
  origin: "human",
  model_name: null,
  prompt_version: null,
  created_by: rudo,
  created_at: "2026-11-10T09:00:00Z",
  ...o,
});

const detail = (o: Partial<StoryDetail> = {}): StoryDetail => ({
  ...summary(),
  verification: { note: "Phoned the council.", at: "2026-11-10T08:30:00Z", by: rudo },
  article: { id: "a1", headline: "Budget presented", publisher: "The Herald", source_url: "https://herald.example/b", published_at: null },
  scripts: [],
  reviews: [],
  reading_wpm: 150,
  ...o,
});

const article = { id: "a1", article_text: "Full article text about the budget.", excerpt: null } as unknown as NewsroomArticleDetail;

beforeEach(() => {
  vi.clearAllMocks();
  asReporter();
  api.getNewsroomArticle.mockResolvedValue(article);
  api.listAssignees.mockResolvedValue([]);
  api.getStory.mockResolvedValue(detail());
});

/* ------------------------------------------------------------------ board */

describe("Story board", () => {
  const stories = [
    summary({ id: "s1", title: "Assigned story", stage: "assigned", verified: false }),
    summary({ id: "s2", title: "Drafting story", stage: "drafting", latest_script_version: 2, latest_script_seconds: 75 }),
    summary({ id: "s3", title: "Waiting story", stage: "in_review", assignee: thabo, updated_at: "2026-11-09T09:00:00Z" }),
    summary({ id: "s4", title: "Another waiting", stage: "in_review", updated_at: "2026-11-11T09:00:00Z" }),
    summary({ id: "s5", title: "Late story", stage: "drafting", deadline_at: "2020-01-01T00:00:00Z" }),
    summary({ id: "s6", title: "Approved story", stage: "approved", deadline_at: "2020-01-01T00:00:00Z", approved_script_version: 1 }),
  ];
  beforeEach(() => {
    api.listStories.mockResolvedValue({ items: stories, total: stories.length, page: 1, page_size: 100 });
  });

  it("asks only for the stages on the board", async () => {
    render(<StoryBoard />);
    await screen.findByText("Assigned story");
    expect(api.listStories).toHaveBeenCalledWith(expect.objectContaining({ stage: BOARD_STAGES, pageSize: 100 }));
  });

  it("has a column per stage with counts and puts each story in its own", async () => {
    render(<StoryBoard />);
    await screen.findByText("Assigned story");
    const column = (name: string) => screen.getByRole("region", { name: new RegExp(`^${name}`) });
    expect(within(column("Assigned")).getByText("Assigned story")).toBeInTheDocument();
    expect(within(column("Drafting")).getByText("Drafting story")).toBeInTheDocument();
    expect(within(column("Awaiting approval")).getByText("Waiting story")).toBeInTheDocument();
    expect(within(column("Awaiting approval")).getByText("2")).toBeInTheDocument(); // the count
    expect(within(column("Approved")).getByText("Approved story")).toBeInTheDocument();
    expect(within(column("Sent back")).getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(BOARD_STAGES.length);
  });

  it("shows the reporter, the deadline and the reading time on each card", async () => {
    render(<StoryBoard />);
    const card = (await screen.findByText("Drafting story")).closest("li")!;
    expect(within(card).getByText("Rudo Reporter")).toBeInTheDocument();
    expect(within(card).getByText(/1 Jan/)).toBeInTheDocument();
    expect(within(card).getByText("1:15 · v2")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Drafting story" })).toHaveAttribute("href", "/stories/s2");
    const assigned = screen.getByText("Assigned story").closest("li")!;
    expect(within(assigned).getByText("Not verified")).toBeInTheDocument();
  });

  it("flags a missed deadline in words, but not on an approved story", async () => {
    render(<StoryBoard />);
    const late = (await screen.findByText("Late story")).closest("li")!;
    expect(within(late).getByText(/Overdue/)).toBeInTheDocument();
    const approved = screen.getByText("Approved story").closest("li")!;
    expect(within(approved).queryByText(/Overdue/)).not.toBeInTheDocument();
  });

  it("gives the Executive Producer an approval queue filter, oldest first", async () => {
    asProducer();
    render(<StoryBoard />);
    await screen.findByText("Assigned story");
    await userEvent.click(screen.getByRole("button", { name: "Awaiting approval (2)" }));
    const rows = within(screen.getByRole("list", { name: "Awaiting approval" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Waiting story")).toBeInTheDocument(); // 9 Nov before 11 Nov
    expect(within(rows[0]).getByRole("link", { name: "Review" })).toHaveAttribute("href", "/stories/s3");
    expect(screen.queryByText("Assigned story")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Board" }));
    expect(await screen.findByText("Assigned story")).toBeInTheDocument();
  });

  it("does not offer the approval queue to reporters", async () => {
    render(<StoryBoard />);
    await screen.findByText("Assigned story");
    expect(screen.queryByRole("button", { name: /Awaiting approval/ })).not.toBeInTheDocument();
  });

  it("points a reporter with no stories to the News Monitor", async () => {
    api.listStories.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
    render(<StoryBoard />);
    expect(await screen.findByText("You have no stories yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the News Monitor" })).toHaveAttribute("href", "/news");
  });

  it("shows API errors instead of an empty board", async () => {
    api.listStories.mockRejectedValue(new Error("The API returned 500."));
    render(<StoryBoard />);
    expect(await screen.findByText(/500/)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ workspace */

describe("Story workspace", () => {
  const buttons = () => ({
    save: screen.queryByRole("button", { name: "Save new version" }),
    submit: screen.queryByRole("button", { name: /Submit for approval/ }),
    draft: screen.queryByRole("button", { name: /Draft with AI/ }),
    approve: screen.queryByRole("button", { name: /Approve/ }),
    sendBack: screen.queryByRole("button", { name: /Send back/ }),
  });
  const typeScript = (value: string) => fireEvent.change(screen.getByLabelText("Script"), { target: { value } });

  it("shows the source article beside the script editor", async () => {
    render(<StoryWorkspace id="s1" />);
    expect(await screen.findByText("Full article text about the budget.")).toBeInTheDocument();
    expect(screen.getByLabelText("Script")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Original/ })).toHaveAttribute("href", "https://herald.example/b");
  });

  it("estimates reading time as the reporter types", async () => {
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    typeScript(Array(75).fill("word").join(" "));
    expect(screen.getByText("75 words · about 0:30 to read at 150 words a minute")).toBeInTheDocument();
    typeScript(Array(150).fill("word").join(" "));
    expect(screen.getByText("150 words · about 1:00 to read at 150 words a minute")).toBeInTheDocument();
  });

  it("saves a new version against the version on screen", async () => {
    api.getStory.mockResolvedValue(detail({ scripts: [script(1)], latest_script_version: 1 }));
    api.saveScript.mockResolvedValue(detail());
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(buttons().save).toBeDisabled(); // nothing changed yet
    typeScript("A rewritten script.");
    await userEvent.click(buttons().save!);
    await waitFor(() =>
      expect(api.saveScript).toHaveBeenCalledWith("s1", { headline: "Headline v1", body: "A rewritten script.", baseVersion: 1 }),
    );
  });

  it("will not submit until verified, saved and unchanged, and says why", async () => {
    api.getStory.mockResolvedValue(detail({ verified: false, verification: null, scripts: [script(1)], latest_script_version: 1 }));
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(buttons().submit).toBeDisabled();
    expect(screen.getByText("Record how the story was verified before submitting.")).toBeInTheDocument();
  });

  it("submits a verified, saved script for approval", async () => {
    api.getStory.mockResolvedValue(detail({ scripts: [script(1)], latest_script_version: 1 }));
    api.submitStory.mockResolvedValue(detail({ stage: "in_review" }));
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(buttons().submit).toBeEnabled();
    typeScript("Edited but not saved.");
    expect(buttons().submit).toBeDisabled();
    expect(screen.getByText("Save your changes before submitting.")).toBeInTheDocument();
    typeScript("The council approved the budget, according to The Herald.");
    await userEvent.click(buttons().submit!);
    await waitFor(() => expect(api.submitStory).toHaveBeenCalledWith("s1"));
  });

  it("offers the AI draft only after verification, from a button, and sends the version on screen", async () => {
    api.getStory.mockResolvedValue(detail({ verified: false, verification: null }));
    const { unmount } = render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(buttons().draft).toBeDisabled();
    expect(screen.getByText("Available after you record verification.")).toBeInTheDocument();
    expect(api.draftScript).not.toHaveBeenCalled(); // never automatic
    unmount();

    api.getStory.mockResolvedValue(detail({ scripts: [script(1)], latest_script_version: 1 }));
    api.draftScript.mockResolvedValue(detail());
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(api.draftScript).not.toHaveBeenCalled();
    expect(buttons().draft).toBeEnabled();
    await userEvent.click(buttons().draft!);
    await waitFor(() => expect(api.draftScript).toHaveBeenCalledWith("s1", { baseVersion: 1, targetSeconds: 45 }));
  });

  it("will not draft over unsaved edits or for an original story", async () => {
    api.getStory.mockResolvedValue(detail({ scripts: [script(1)], latest_script_version: 1 }));
    const { unmount } = render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    typeScript("Unsaved change");
    expect(buttons().draft).toBeDisabled();
    expect(screen.getByText(/Save or undo your changes first/)).toBeInTheDocument();
    unmount();

    api.getStory.mockResolvedValue(detail({ source_item_id: null, article: null }));
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(buttons().draft).toBeDisabled();
    expect(screen.getByText("Available for stories built from an article.")).toBeInTheDocument();
  });

  it("labels an AI draft and tells the reporter to check it", async () => {
    api.getStory.mockResolvedValue(
      detail({ scripts: [script(1, { origin: "ai_draft", model_name: "gpt-test" })], latest_script_version: 1 }),
    );
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Script");
    expect(screen.getAllByText("AI draft").length).toBeGreaterThan(0);
    expect(screen.getByText(/Check every fact against the article/)).toBeInTheDocument();
    typeScript("Edited by a person.");
    expect(screen.queryByText(/Check every fact against the article/)).not.toBeInTheDocument();
  });

  it("shows the Executive Producer's comment when a story is sent back", async () => {
    api.getStory.mockResolvedValue(
      detail({
        stage: "changes_requested",
        scripts: [script(1)],
        latest_script_version: 1,
        reviews: [{ id: "r1", script_id: "sc1", script_version: 1, decision: "changes_requested", comment: "Attribute the figures.", self_approved: false, reviewer: esther, reviewed_at: "2026-11-10T10:00:00Z" }],
      }),
    );
    render(<StoryWorkspace id="s1" />);
    const banner = (await screen.findByText(/Sent back by Esther Producer:/)).closest("p")!;
    expect(banner).toHaveTextContent("Attribute the figures.");
  });

  describe("approval", () => {
    const inReview = (o: Partial<StoryDetail> = {}) =>
      detail({ stage: "in_review", scripts: [script(2)], latest_script_version: 2, ...o });

    it("gives the Executive Producer approve and send back, for the version in front of them", async () => {
      asProducer();
      api.getStory.mockResolvedValue(inReview());
      api.reviewStory.mockResolvedValue(detail({ stage: "approved" }));
      render(<StoryWorkspace id="s1" />);
      await screen.findByText(/Version 2 is waiting for you/);
      expect(buttons().sendBack).toBeDisabled(); // a comment is required to send back
      await userEvent.type(screen.getByLabelText("Review comment"), "Looks good");
      await userEvent.click(buttons().approve!);
      await waitFor(() => expect(api.reviewStory).toHaveBeenCalledWith("s1", { decision: "approved", scriptVersion: 2, comment: "Looks good" }));
    });

    it("sends a story back with a comment", async () => {
      asProducer();
      api.getStory.mockResolvedValue(inReview());
      api.reviewStory.mockResolvedValue(detail({ stage: "changes_requested" }));
      render(<StoryWorkspace id="s1" />);
      await screen.findByLabelText("Review comment");
      await userEvent.type(screen.getByLabelText("Review comment"), "Shorten it");
      expect(buttons().sendBack).toBeEnabled();
      await userEvent.click(buttons().sendBack!);
      await waitFor(() => expect(api.reviewStory).toHaveBeenCalledWith("s1", { decision: "changes_requested", scriptVersion: 2, comment: "Shorten it" }));
    });

    it("warns, but allows, approving a story the Executive Producer owns", async () => {
      asProducer();
      api.getStory.mockResolvedValue(inReview({ assignee: esther }));
      render(<StoryWorkspace id="s1" />);
      expect(await screen.findByText(/recorded as self-approved/)).toBeInTheDocument();
      expect(buttons().approve).toBeEnabled();
    });

    it("never shows approval controls to a reporter, even for their own story", async () => {
      api.getStory.mockResolvedValue(inReview());
      render(<StoryWorkspace id="s1" />);
      await screen.findByRole("heading", { name: "Headline v2" });
      expect(buttons().approve).not.toBeInTheDocument();
      expect(buttons().sendBack).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Review comment")).not.toBeInTheDocument();
      // and the script is read-only while it waits
      expect(screen.queryByLabelText("Script")).not.toBeInTheDocument();
      expect(buttons().save).not.toBeInTheDocument();
    });

    it("marks a self-approved decision in the history", async () => {
      asProducer();
      api.getStory.mockResolvedValue(
        detail({
          stage: "approved",
          scripts: [script(1)],
          latest_script_version: 1,
          approved_script_version: 1,
          reviews: [{ id: "r1", script_id: "sc1", script_version: 1, decision: "approved", comment: null, self_approved: true, reviewer: esther, reviewed_at: "2026-11-10T10:00:00Z" }],
        }),
      );
      render(<StoryWorkspace id="s1" />);
      expect(await screen.findByText("Self-approved")).toBeInTheDocument();
      expect(screen.getByText(/Approved version 1/)).toBeInTheDocument();
    });
  });

  describe("roles", () => {
    it("is read-only for an analyst", async () => {
      asAnalyst();
      api.getStory.mockResolvedValue(detail({ scripts: [script(1)], latest_script_version: 1 }));
      render(<StoryWorkspace id="s1" />);
      await screen.findByRole("heading", { name: "Headline v1" });
      for (const b of Object.values(buttons())) expect(b).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Script")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Verification note")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Drop story" })).not.toBeInTheDocument();
    });

    it("does not let a reporter edit another reporter's story", async () => {
      api.getStory.mockResolvedValue(detail({ assignee: thabo, scripts: [script(1)], latest_script_version: 1 }));
      render(<StoryWorkspace id="s1" />);
      await screen.findByRole("heading", { name: "Headline v1" });
      expect(screen.queryByLabelText("Script")).not.toBeInTheDocument();
    });

    it("lets the Executive Producer edit any story", async () => {
      asProducer();
      api.getStory.mockResolvedValue(detail({ assignee: thabo }));
      render(<StoryWorkspace id="s1" />);
      expect(await screen.findByLabelText("Script")).toBeInTheDocument();
    });

    it("explains that a story belongs to another reporter when the server says so", async () => {
      const { ApiError } = await import("@/lib/api/errors");
      api.getStory.mockRejectedValue(new ApiError("This story belongs to another reporter.", 403));
      render(<StoryWorkspace id="s1" />);
      expect(await screen.findByText("This story belongs to another reporter")).toBeInTheDocument();
    });

    it("explains a missing story", async () => {
      const { ApiError } = await import("@/lib/api/errors");
      api.getStory.mockRejectedValue(new ApiError("No such story.", 404));
      render(<StoryWorkspace id="s1" />);
      expect(await screen.findByText(/Back to Stories/)).toBeInTheDocument();
    });
  });

  it("records verification and drops a story only after confirming", async () => {
    api.getStory.mockResolvedValue(detail({ verified: false, verification: null }));
    api.verifyStory.mockResolvedValue(detail());
    api.dropStory.mockResolvedValue(detail({ stage: "dropped" }));
    render(<StoryWorkspace id="s1" />);
    await screen.findByLabelText("Verification note");
    expect(screen.getByRole("button", { name: "Record verification" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Verification note"), "Checked the minutes");
    await userEvent.click(screen.getByRole("button", { name: "Record verification" }));
    await waitFor(() => expect(api.verifyStory).toHaveBeenCalledWith("s1", "Checked the minutes"));

    await userEvent.click(screen.getByRole("button", { name: "Drop story" }));
    expect(api.dropStory).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, drop it" }));
    await waitFor(() => expect(api.dropStory).toHaveBeenCalledWith("s1"));
  });

  it("explains that editing an approved script needs approval again", async () => {
    api.getStory.mockResolvedValue(
      detail({ stage: "approved", scripts: [script(1)], latest_script_version: 1, approved_script_version: 1 }),
    );
    render(<StoryWorkspace id="s1" />);
    expect(await screen.findByText(/needs approval again/)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ article page card */

describe("Story card on the article page", () => {
  const link = (o: Partial<StoryLink> = {}): StoryLink => ({ id: "s1", title: "Council approves budget", stage: "in_review", assignee: rudo, ...o });

  it("lets a reporter take the story and opens it", async () => {
    api.takeStory.mockResolvedValue(detail({ id: "new-story" }));
    render(<ArticleStoryCard articleId="a1" story={null} onChanged={vi.fn()} />);
    expect(screen.queryByLabelText("Assign to")).not.toBeInTheDocument(); // reporters only take stories for themselves
    await userEvent.click(screen.getByRole("button", { name: "Take this story" }));
    await waitFor(() => expect(api.takeStory).toHaveBeenCalledWith({ sourceItemId: "a1", assigneeId: undefined }));
    expect(nav.push).toHaveBeenCalledWith("/stories/new-story");
  });

  it("gives the Executive Producer an assignee picker", async () => {
    asProducer();
    api.listAssignees.mockResolvedValue([{ ...esther, role: "editor" }, { ...rudo, role: "reporter" }, { ...thabo, role: "reporter" }]);
    api.takeStory.mockResolvedValue(detail({ id: "s9" }));
    render(<ArticleStoryCard articleId="a1" story={null} onChanged={vi.fn()} />);
    const picker = await screen.findByLabelText("Assign to");
    await within(picker).findByRole("option", { name: "Thabo Other" });
    expect(within(picker).queryByRole("option", { name: "Esther Producer" })).not.toBeInTheDocument(); // "Me" covers it
    expect(screen.getByRole("button", { name: "Take this story" })).toBeInTheDocument();
    await userEvent.selectOptions(picker, "u-other");
    await userEvent.click(screen.getByRole("button", { name: "Assign this story" }));
    await waitFor(() => expect(api.takeStory).toHaveBeenCalledWith({ sourceItemId: "a1", assigneeId: "u-other" }));
  });

  it("shows the linked story, its stage and who has it", () => {
    render(<ArticleStoryCard articleId="a1" story={link()} onChanged={vi.fn()} />);
    expect(screen.getByText("Awaiting approval")).toBeInTheDocument();
    expect(screen.getByText("with Rudo Reporter")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Council approves budget" })).toHaveAttribute("href", "/stories/s1");
    expect(screen.queryByRole("button", { name: "Take this story" })).not.toBeInTheDocument();
  });

  it("does not link a reporter to another reporter's story, which they cannot open", () => {
    render(<ArticleStoryCard articleId="a1" story={link({ assignee: thabo })} onChanged={vi.fn()} />);
    expect(screen.getByText("with Thabo Other")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Council approves budget" })).not.toBeInTheDocument();
  });

  it("offers nothing to take for an analyst", () => {
    asAnalyst();
    render(<ArticleStoryCard articleId="a1" story={null} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Take this story" })).not.toBeInTheDocument();
    expect(screen.getByText(/Nobody has taken this article/)).toBeInTheDocument();
  });

  it("refreshes the card when someone else took the article first", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    const onChanged = vi.fn();
    api.takeStory.mockRejectedValue(new ApiError("Someone has already taken this article.", 409));
    render(<ArticleStoryCard articleId="a1" story={null} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("button", { name: "Take this story" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(nav.push).not.toHaveBeenCalled();
  });
});
