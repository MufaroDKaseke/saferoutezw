import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Resource } from "@/hooks/use-resource";
import { EndpointNotAvailableError, NotFoundError } from "@/lib/api/errors";
import { ResourceView } from "./resource-view";
import { EmptyState, QueryError } from "./states";

function resource<T>(partial: Partial<Resource<T>>): Resource<T> {
  return { data: undefined, error: null, isLoading: false, isFetching: false, refetch: () => {}, ...partial };
}

describe("QueryError", () => {
  it("explains a missing endpoint without inventing data", () => {
    render(<QueryError error={new EndpointNotAvailableError("GET /api/v1/news")} />);
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
    expect(screen.getByText("GET /api/v1/news")).toBeInTheDocument();
    expect(screen.getByText(/No numbers have\s+been made up/)).toBeInTheDocument();
    expect(screen.getByText(/NEXT_PUBLIC_DATA_MODE=mock/)).toBeInTheDocument();
  });

  it("explains a record that does not exist", () => {
    render(<QueryError error={new NotFoundError("Incident")} what="incident" />);
    expect(screen.getByText("We could not find that incident")).toBeInTheDocument();
  });

  it("offers a retry for an ordinary failure", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<QueryError error={new Error("The API returned 503.")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The API returned 503.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
  });
});

describe("ResourceView", () => {
  it("shows the skeleton while loading", () => {
    render(
      <ResourceView resource={resource<string>({ isLoading: true })} skeleton={<p>loading skeleton</p>}>
        {(d) => <p>{d}</p>}
      </ResourceView>,
    );
    expect(screen.getByText("loading skeleton")).toBeInTheDocument();
  });

  it("shows the error state instead of stale data", () => {
    render(
      <ResourceView resource={resource<string>({ error: new EndpointNotAvailableError("GET /x") })}>{(d) => <p>{d}</p>}</ResourceView>,
    );
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
  });

  it("renders data when it has loaded", () => {
    render(<ResourceView resource={resource({ data: "real data" })}>{(d) => <p>{d}</p>}</ResourceView>);
    expect(screen.getByText("real data")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("tells the reader what to do next", () => {
    render(<EmptyState title="No articles match these filters" description="Try removing a filter." />);
    expect(screen.getByRole("heading", { name: "No articles match these filters" })).toBeInTheDocument();
    expect(screen.getByText("Try removing a filter.")).toBeInTheDocument();
  });
});
