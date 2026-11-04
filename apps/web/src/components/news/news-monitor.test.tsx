import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { toClassification } from "@/lib/api/live/mappers";
import { NewsMonitor } from "./news-monitor";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/news",
  useSearchParams: () => new URLSearchParams(),
}));

describe("News Monitor category filter (demo data)", () => {
  it("offers the category chips next to the existing filters", async () => {
    render(<NewsMonitor />);
    expect(await screen.findByRole("group", { name: "Filter by category" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Road Incidents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Transport Policy" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search headline")).toBeInTheDocument();
  });

  it("narrows the list to a category and shows an empty state when nothing matches", async () => {
    render(<NewsMonitor />);
    await waitFor(() => expect(screen.getAllByRole("row").length).toBeGreaterThan(2));
    const all = screen.getAllByRole("row").length;

    await userEvent.click(screen.getByRole("button", { name: "Transport Policy" }));
    expect(await screen.findByText("No articles match these filters")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(all));
  });

  it("keeps demo incident-linked articles under Road Incidents", async () => {
    render(<NewsMonitor />);
    await userEvent.click(await screen.findByRole("button", { name: "Road Incidents" }));
    await waitFor(() => expect(screen.getAllByText(/Evidence for/).length).toBeGreaterThan(0));
    expect(screen.queryByText("No articles match these filters")).not.toBeInTheDocument();
  });
});

describe("toClassification", () => {
  it("maps the API block without inventing values", () => {
    const c = toClassification({
      status: "awaiting_classification",
      primary_category: null,
      primary_subtype: null,
      candidate_categories: ["road_incident", "traffic_disruption"],
      record_kind: null,
      geographic_scope: null,
      geographic_relevance: "zimbabwe",
      editorial_status: null,
      intelligence_record_id: null,
      linked_incident_id: null,
    });
    expect(c.primaryCategory).toBeNull();
    expect(c.recordKind).toBeNull();
    expect(c.candidateCategories).toEqual(["road_incident", "traffic_disruption"]);
    expect(c.geographicRelevance).toBe("zimbabwe");
  });

  it("carries a classified record with its linked event", () => {
    const c = toClassification({
      status: "classified",
      primary_category: "road_infrastructure",
      primary_subtype: "road_rehabilitation",
      candidate_categories: [],
      record_kind: "informational_development",
      geographic_scope: "corridor",
      geographic_relevance: "zimbabwe",
      editorial_status: "candidate",
      intelligence_record_id: "r1",
      linked_incident_id: null,
    });
    expect(c).toMatchObject({ status: "classified", primaryCategory: "road_infrastructure", linkedIncidentId: null, intelligenceRecordId: "r1" });
  });
});
