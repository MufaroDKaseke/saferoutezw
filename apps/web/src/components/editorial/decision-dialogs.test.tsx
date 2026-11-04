import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { checkBulletin } from "@/lib/domain/bulletin-checks";
import { ApproveDialog, RejectDialog, RequestChangesDialog } from "./decision-dialogs";

describe("RejectDialog", () => {
  it("requires a reason of at least 10 characters", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<RejectDialog open onOpenChange={() => {}} pending={false} onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "Reject report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 10 characters/);
    expect(onConfirm).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Reason for rejecting"), "too short");
    await user.click(screen.getByRole("button", { name: "Reject report" }));
    expect(onConfirm).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Reason for rejecting"));
    await user.type(screen.getByLabelText("Reason for rejecting"), "A court follow-up, not a current incident.");
    await user.click(screen.getByRole("button", { name: "Reject report" }));
    expect(onConfirm).toHaveBeenCalledWith("A court follow-up, not a current incident.");
  });

  it("marks the field invalid for assistive technology", async () => {
    const user = userEvent.setup();
    render(<RejectDialog open onOpenChange={() => {}} pending={false} onConfirm={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Reject report" }));
    expect(screen.getByLabelText("Reason for rejecting")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("RequestChangesDialog", () => {
  it("requires notes", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<RequestChangesDialog open onOpenChange={() => {}} pending={false} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Request changes" }));
    expect(onConfirm).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("What needs to change?"), "Confirm the location on the A4.");
    await user.click(screen.getByRole("button", { name: "Request changes" }));
    expect(onConfirm).toHaveBeenCalledWith("Confirm the location on the A4.");
  });
});

describe("ApproveDialog", () => {
  const base = {
    open: true,
    onOpenChange: () => {},
    referenceCode: "SR-0412",
    incidentType: "collision" as const,
    headline: "Head-on collision reported on A3 near Rusape",
    versionLabel: "Bulletin version 1 · SafeRouteZW AI (AI draft)",
    pending: false,
  };

  it("shows the exact bulletin, its version, the checks and a simulation notice", () => {
    const body = "A head-on collision has been reported on the A3 near Rusape. It has not been confirmed.";
    render(<ApproveDialog {...base} body={body} checks={checkBulletin(base.headline, body, "unconfirmed")} onConfirm={() => {}} />);
    expect(screen.getByRole("heading", { name: "Approve this exact bulletin?" })).toBeInTheDocument();
    expect(screen.getByText(base.headline)).toBeInTheDocument();
    expect(screen.getByText(body)).toBeInTheDocument();
    expect(screen.getByText(/Bulletin version 1/)).toBeInTheDocument();
    expect(screen.getByText(/Location: Unconfirmed/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is published or sent/)).toBeInTheDocument();
  });

  it("needs an explicit click, and never confirms on its own", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const body = "A head-on collision has been reported. It has not been confirmed.";
    render(<ApproveDialog {...base} body={body} checks={checkBulletin(base.headline, body, "second_source")} onConfirm={onConfirm} />);
    expect(onConfirm).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Confirm approval/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables approval while the wording contains sender details", () => {
    const body = "Call +263 77 123 4567 to report. A collision has been reported.";
    render(<ApproveDialog {...base} body={body} checks={checkBulletin(base.headline, body, "second_source")} onConfirm={() => {}} />);
    expect(screen.getByRole("button", { name: /Confirm approval/ })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/disabled until the wording problem/i);
  });

  it("can be cancelled without approving", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    const body = "A collision has been reported. It has not been confirmed.";
    render(<ApproveDialog {...base} onOpenChange={onOpenChange} body={body} checks={checkBulletin(base.headline, body, "official")} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
