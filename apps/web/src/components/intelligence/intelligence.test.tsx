import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { IntelligenceOverview, IntelligenceStatistics } from "@/lib/api/intelligence";
import { RecordKindBadge, RecordStatusBadge } from "./badges";
import { CategoryFilter } from "./category-filter";
import { categoryChartRows, IntelligenceOverviewBody } from "./overview-panel";
import { seriesRows, StatisticsPanel } from "./statistics-charts";

function obs(over: Partial<IntelligenceStatistics["series"][number]["points"][number]> = {}) {
  return {
    id: "o1",
    record_id: "r1",
    metric: "road deaths",
    value: 1800,
    unit: "persons",
    period_start: "2025-01-01",
    period_end: "2025-12-31",
    geographic_coverage: "Zimbabwe",
    source_reference: "Zimbabwe Republic Police",
    methodology: null,
    comparison_period: null,
    is_preliminary: false,
    verification_status: "verified",
    ...over,
  };
}

describe("CategoryFilter", () => {
  it("renders every filter and marks the selected one", () => {
    render(<CategoryFilter value="road_hazard" onChange={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(10);
    expect(screen.getByRole("button", { name: "Road Hazards" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
  });

  it("reports the chosen category", async () => {
    const onChange = vi.fn();
    render(<CategoryFilter value="all" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Transport Policy" }));
    expect(onChange).toHaveBeenCalledWith("transport_policy");
  });

  it("shows counts when given", () => {
    render(<CategoryFilter value="all" onChange={() => {}} counts={{ road_incident: 7 }} />);
    expect(within(screen.getByRole("button", { name: /Road Incidents/ })).getByText("7")).toBeInTheDocument();
  });
});

describe("badges", () => {
  it("says in words whether a record is an event or a report", () => {
    render(<><RecordKindBadge kind="actionable_event" /><RecordKindBadge kind="statistical_report" /></>);
    expect(screen.getByText("Actionable event")).toBeInTheDocument();
    expect(screen.getByText("Statistical report")).toBeInTheDocument();
  });

  it("labels editorial status", () => {
    render(<RecordStatusBadge status="under_review" />);
    expect(screen.getByText("Under review")).toBeInTheDocument();
  });
});

describe("StatisticsPanel", () => {
  it("shows an honest empty state", () => {
    render(<StatisticsPanel data={{ series: [], note: "n" }} />);
    expect(screen.getByText(/No statistical figures have been extracted yet/)).toBeInTheDocument();
  });

  it("shows period, source, coverage, verification and the no-summing note", () => {
    const data: IntelligenceStatistics = {
      note: "Figures are not added together.",
      series: [{ metric: "road deaths", unit: "persons", geographic_coverage: "Zimbabwe", points: [obs(), obs({ id: "o2", period_start: "2024-01-01", period_end: "2024-12-31", value: 1700, is_preliminary: true, verification_status: "unverified" })] }],
    };
    render(<StatisticsPanel data={data} />);
    expect(screen.getByText("Figures are not added together.")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("2025")).toBeInTheDocument();
    expect(within(table).getByText("2024")).toBeInTheDocument();
    expect(within(table).getByText("1,800 persons")).toBeInTheDocument();
    expect(within(table).getAllByText("Zimbabwe Republic Police")).toHaveLength(2);
    expect(within(table).getByText("Verified by an editor")).toBeInTheDocument();
    expect(within(table).getByText("Not yet verified")).toBeInTheDocument();
    expect(within(table).getByText("Preliminary")).toBeInTheDocument();
  });

  it("warns when one series mixes sources", () => {
    const data: IntelligenceStatistics = {
      note: "n",
      series: [{ metric: "road deaths", unit: "persons", geographic_coverage: "Zimbabwe", points: [obs(), obs({ id: "o2", source_reference: "A news report" })] }],
    };
    render(<StatisticsPanel data={data} />);
    expect(screen.getByText(/come from different sources/)).toBeInTheDocument();
  });

  it("keeps each point's own period and source", () => {
    const rows = seriesRows([obs({ source_reference: null, period_start: null, period_end: null })]);
    expect(rows[0]).toMatchObject({ period: "Period not stated", source: "Source not stated", preliminary: false });
  });
});

describe("IntelligenceOverviewBody", () => {
  const empty: IntelligenceOverview = { by_category: [], awaiting_review: 0, published_by_output: {}, recent: [], latest_statistics: [] };

  it("shows graceful empty states and invents no counts", () => {
    render(<IntelligenceOverviewBody data={empty} />);
    expect(screen.getByText("No classified records yet.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is published yet.")).toBeInTheDocument();
    expect(screen.getByText("No statistical figures yet.")).toBeInTheDocument();
    expect(screen.getByText("No records yet.")).toBeInTheDocument();
  });

  it("charts only categories that have records", () => {
    const data: IntelligenceOverview = {
      ...empty,
      by_category: [
        { category: "road_incident", label: "Road incidents", subtypes: [], total: 0, awaiting_review: 0, published: 0 },
        { category: "transport_policy", label: "Transport policy", subtypes: [], total: 3, awaiting_review: 2, published: 1 },
      ],
      awaiting_review: 2,
      published_by_output: { transport_news: 1 },
    };
    expect(categoryChartRows(data)).toEqual([{ category: "Transport policy", total: 3, awaiting: 2, published: 1 }]);
    render(<IntelligenceOverviewBody data={data} />);
    expect(screen.getByText("Transport news item:")).toBeInTheDocument();
  });
});
