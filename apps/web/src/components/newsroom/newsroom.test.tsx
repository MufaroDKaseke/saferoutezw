import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getNavGroups, getSectionBySegment } from "@/components/layout/nav-config";
import { ROAD_ROUTE_PREFIXES } from "@/lib/app-mode";
import type { NewsroomArticle, NewsroomArticleDetail, NewsroomSummary } from "@/lib/newsroom/types";
import { NEWS_CATEGORIES, NEWS_CATEGORY_LABEL, newsCategoryLabel } from "@/lib/newsroom/taxonomy";
import { NewsroomArticleDetail as ArticleDetailView } from "./newsroom-article-detail";
import { NewsroomDashboard } from "./newsroom-dashboard";
import { NewsroomMonitor } from "./newsroom-monitor";

const api = vi.hoisted(() => ({
  listNewsroomArticles: vi.fn(),
  getNewsroomArticle: vi.fn(),
  getNewsroomSummary: vi.fn(),
  setArticleReview: vi.fn(),
  retryNewsroomArticle: vi.fn(),
  takeStory: vi.fn(),
  listAssignees: vi.fn(),
  listSources: vi.fn(),
}));

vi.mock("@/lib/api/newsroom", () => ({
  listNewsroomArticles: api.listNewsroomArticles,
  getNewsroomArticle: api.getNewsroomArticle,
  getNewsroomSummary: api.getNewsroomSummary,
  setArticleReview: api.setArticleReview,
  retryNewsroomArticle: api.retryNewsroomArticle,
  takeStory: api.takeStory,
  listAssignees: api.listAssignees,
}));
vi.mock("@/lib/api/sources", () => ({ listSources: api.listSources }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/news",
  useSearchParams: () => new URLSearchParams(),
}));

const article = (overrides: Partial<NewsroomArticle> = {}): NewsroomArticle => ({
  id: "a1",
  publisher_id: "p1",
  publisher: "The Herald",
  headline: "Budget presented to Parliament",
  source_url: "https://herald.example/budget",
  published_at: "2026-11-10T08:00:00Z",
  collected_at: "2026-11-10T08:05:00Z",
  state: "classified",
  processing_status: "processed",
  category: "politics_governance",
  secondary_category: null,
  summary: "The finance minister presented the national budget.",
  geographic_relevance: "zimbabwe_wide",
  needs_editorial_attention: false,
  classification_basis: "full_text",
  review: { status: "new", by: null, at: null, note: null },
  ...overrides,
});

const detail = (overrides: Partial<NewsroomArticleDetail> = {}): NewsroomArticleDetail => ({
  ...article(),
  excerpt: "Feed excerpt",
  article_text: "Full article text",
  topics: ["budget"],
  organisations: ["Treasury"],
  places: ["Harare"],
  attention_reason: null,
  classification_confidence: 0.9,
  model: "gpt-test",
  prompt_version: "newsroom-v1",
  classified_at: "2026-11-10T08:06:00Z",
  reused_from: null,
  fetch_error: null,
  last_error: null,
  story: null,
  ...overrides,
});

const summary = (overrides: Partial<NewsroomSummary> = {}): NewsroomSummary => ({
  total_articles: 5668,
  collected_today: 120,
  classified_today: 95,
  pending_classification: 25,
  failures: 2,
  feeds: { enabled: 22, healthy: 19, unhealthy: 3, disabled: 0 },
  usage_today: { input_tokens: 1000, output_tokens: 500, estimated_cost_usd: null },
  by_category: NEWS_CATEGORIES.map((key, i) => ({ key, label: NEWS_CATEGORY_LABEL[key], count: i })),
  publishers: [{ id: "p1", name: "The Herald", articles: 40, classified: 30 }],
  workflow: { stories_awaiting_approval: 0, stories_in_progress: 0, bulletins_awaiting_approval: 0, next_bulletin: null },
  generated_at: "2026-11-10T09:00:00Z",
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  api.listNewsroomArticles.mockResolvedValue({ items: [article()], total: 1, page: 1, page_size: 15 });
  api.listSources.mockResolvedValue([
    { id: "p1", name: "The Herald", connectionStatus: "healthy", lastSuccessfulPollAt: "2026-11-10T08:00:00Z", errorCount: 0 },
  ]);
  api.getNewsroomSummary.mockResolvedValue(summary());
  api.getNewsroomArticle.mockResolvedValue(detail());
  api.listAssignees.mockResolvedValue([]);
});

describe("newsroom navigation", () => {
  it("has no road-safety item in newsroom mode", () => {
    const hrefs = getNavGroups("nust_newsroom").flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toEqual(["/dashboard", "/news", "/stories", "/bulletins", "/studio", "/archive", "/sources", "/processing", "/settings"]);
    for (const prefix of ROAD_ROUTE_PREFIXES) expect(hrefs.some((h) => h.startsWith(prefix))).toBe(false);
  });

  it("has no empty groups and keeps the review badge out of the newsroom menu", () => {
    for (const group of getNavGroups("nust_newsroom")) {
      expect(group.items.length).toBeGreaterThan(0);
      expect(group.items.some((i) => i.badge)).toBe(false);
    }
  });

  it("keeps the whole road-safety menu in road-safety mode", () => {
    const hrefs = getNavGroups("road_safety").flatMap((g) => g.items.map((i) => i.href));
    for (const expected of ["/news", "/incidents", "/map", "/blackspots", "/reviews", "/alerts", "/intelligence"]) {
      expect(hrefs).toContain(expected);
    }
  });

  it("builds breadcrumbs from the mode's own menu", () => {
    expect(getSectionBySegment("nust_newsroom").news?.title).toBe("News Monitor");
    expect(getSectionBySegment("nust_newsroom").stories?.title).toBe("Stories");
    expect(getSectionBySegment("nust_newsroom").incidents).toBeUndefined();
    expect(getSectionBySegment("road_safety").incidents).toBeDefined();
  });
});

describe("newsroom categories", () => {
  it("has the thirteen general categories with readable labels", () => {
    expect(NEWS_CATEGORIES).toHaveLength(13);
    expect(newsCategoryLabel("crime_courts")).toBe("Crime & Courts");
    expect(newsCategoryLabel(null)).toBe("Not classified");
    expect(newsCategoryLabel("something_new")).toBe("something_new");
  });
});

describe("News Monitor (newsroom)", () => {
  it("shows the publisher, summary, category and a link to the original", async () => {
    render(<NewsroomMonitor />);
    expect(await screen.findByText("Budget presented to Parliament")).toBeInTheDocument();
    expect(screen.getByText("The finance minister presented the national budget.")).toBeInTheDocument();
    expect(screen.getAllByText("Politics & Governance").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Original article/ })).toHaveAttribute("href", "https://herald.example/budget");
  });

  it("offers the newsroom filters, not road-safety ones", async () => {
    render(<NewsroomMonitor />);
    await screen.findByText("Budget presented to Parliament");
    for (const label of ["Search headlines and text", "Publisher", "Category", "Processing", "Review", "Collected"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText("Keyword match")).not.toBeInTheDocument();
    expect(screen.queryByText(/incident/i)).not.toBeInTheDocument();
  });

  it("searches through the API", async () => {
    render(<NewsroomMonitor />);
    await screen.findByText("Budget presented to Parliament");
    await userEvent.type(screen.getByLabelText("Search headlines and text"), "nust");
    await waitFor(() => expect(api.listNewsroomArticles).toHaveBeenLastCalledWith(expect.objectContaining({ q: "nust", page: 1 })));
  });

  it("says so when nothing matches", async () => {
    api.listNewsroomArticles.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 15 });
    render(<NewsroomMonitor />);
    expect(await screen.findByText("No articles match these filters")).toBeInTheDocument();
  });

  it("shows API errors instead of inventing data", async () => {
    api.listNewsroomArticles.mockRejectedValue(new Error("The API returned 500."));
    render(<NewsroomMonitor />);
    expect(await screen.findByText(/500/)).toBeInTheDocument();
  });

  it("marks articles that were read from the excerpt only", async () => {
    api.listNewsroomArticles.mockResolvedValue({
      items: [article({ classification_basis: "excerpt", needs_editorial_attention: true })], total: 1, page: 1, page_size: 15,
    });
    render(<NewsroomMonitor />);
    expect(await screen.findByText("Read from the feed excerpt only")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
  });
});

describe("Newsroom dashboard", () => {
  it("shows the key numbers from the API", async () => {
    render(<NewsroomDashboard />);
    expect(await screen.findByText("5,668")).toBeInTheDocument();
    for (const title of ["Collected articles", "Collected today", "Classified today", "Pending classification", "Processing failures", "Healthy RSS feeds"]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.getByText("19 / 22")).toBeInTheDocument();
    expect(screen.getByText("3 need attention")).toBeInTheDocument();
  });

  it("lists the latest articles with their summaries", async () => {
    render(<NewsroomDashboard />);
    expect(await screen.findByText("The finance minister presented the national budget.")).toBeInTheDocument();
    expect(screen.getByText(/No cost estimate/)).toBeInTheDocument();
  });

  it("shows the story-to-air counters and the next bulletin", async () => {
    api.getNewsroomSummary.mockResolvedValue(
      summary({
        workflow: {
          stories_awaiting_approval: 3,
          stories_in_progress: 7,
          bulletins_awaiting_approval: 1,
          next_bulletin: {
            id: "b9", name: "6pm News", scheduled_for: "2099-01-01T16:00:00Z", target_seconds: 300, approved_revision_number: 2,
            approved_at: "2099-01-01T14:00:00Z", approved_total_seconds: 290, latest_revision_number: 2, latest_revision_state: "approved",
            aired_at: null, created_by: { id: "u", display_name: "Esther" }, created_at: "2026-11-12T08:00:00Z",
          },
        },
      }),
    );
    render(<NewsroomDashboard />);
    const awaiting = (await screen.findByText("Stories awaiting approval")).closest("a")!;
    expect(awaiting).toHaveAttribute("href", "/stories");
    expect(within(awaiting).getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Stories in progress").closest("a")).toHaveTextContent("7");
    expect(screen.getByText("Bulletins awaiting approval").closest("a")).toHaveAttribute("href", "/bulletins");
    const next = screen.getByText("Next bulletin").closest("a")!;
    expect(next).toHaveAttribute("href", "/bulletins/b9");
    expect(next).toHaveTextContent("6pm News");
    expect(next).toHaveTextContent("target 5:00");
    expect(next).toHaveTextContent("revision 2 approved");
  });

  it("says when no bulletin is scheduled", async () => {
    render(<NewsroomDashboard />);
    const next = (await screen.findByText("Next bulletin")).closest("a")!;
    expect(next).toHaveTextContent("None scheduled");
    expect(next).toHaveAttribute("href", "/bulletins");
  });

  it("shows the estimated cost only when the API provides one", async () => {
    api.getNewsroomSummary.mockResolvedValue(summary({ usage_today: { input_tokens: 10, output_tokens: 5, estimated_cost_usd: 0.9 } }));
    render(<NewsroomDashboard />);
    expect(await screen.findByText(/about US\$0\.90/)).toBeInTheDocument();
  });
});

describe("Newsroom article page", () => {
  it("shows the summary, entities and a plain statement of what confidence means", async () => {
    render(<ArticleDetailView id="a1" />);
    expect(await screen.findByText("Treasury")).toBeInTheDocument();
    expect(screen.getByText("budget")).toBeInTheDocument();
    expect(screen.getByText("Full article text")).toBeInTheDocument();
    expect(screen.getByText(/not the chance that the article is true/)).toBeInTheDocument();
    expect(screen.getByText(/does not check facts/)).toBeInTheDocument();
  });

  it("sets the review flag", async () => {
    api.setArticleReview.mockResolvedValue(detail({ review: { status: "used", by: "Ed", at: "2026-11-10T09:00:00Z", note: null } }));
    render(<ArticleDetailView id="a1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Used" }));
    await waitFor(() => expect(api.setArticleReview).toHaveBeenCalledWith("a1", "used", ""));
  });

  it("offers to try a failed article again", async () => {
    api.getNewsroomArticle.mockResolvedValue(detail({ state: "failed", summary: null, category: null, last_error: "OpenAI call failed" }));
    api.retryNewsroomArticle.mockResolvedValue(detail({ state: "pending" }));
    render(<ArticleDetailView id="a1" />);
    await userEvent.click(await screen.findByRole("button", { name: /Try again/ }));
    await waitFor(() => expect(api.retryNewsroomArticle).toHaveBeenCalledWith("a1"));
  });

  it("explains a missing article", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    api.getNewsroomArticle.mockRejectedValue(new ApiError("No such article.", 404));
    render(<ArticleDetailView id="missing" />);
    expect(await screen.findByText(/Back to the News Monitor/)).toBeInTheDocument();
  });
});
