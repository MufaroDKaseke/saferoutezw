import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChangePassword } from "./change-password";
import { passwordProblem } from "./password-fields";

const auth = vi.hoisted(() => ({ changePassword: vi.fn(), clearLocalSession: vi.fn(), replace: vi.fn() }));
vi.mock("@/lib/api/auth", () => ({ changePassword: auth.changePassword }));
vi.mock("@/hooks/use-demo-session", () => ({ clearLocalSession: auth.clearLocalSession }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: auth.replace }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

beforeEach(() => { vi.clearAllMocks(); auth.changePassword.mockResolvedValue(undefined); });

describe("changing your password", () => {
  it("checks passphrase length using characters and requires matching confirmation", () => {
    expect(passwordProblem("🦁".repeat(6), "🦁".repeat(6))).toMatch(/12 characters/);
    expect(passwordProblem("long enough phrase", "different phrase")).toMatch(/do not match/);
  });

  it("requires the current password before calling the API", async () => {
    render(<ChangePassword />);
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your current password");
    expect(auth.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password, clears the session and returns to sign in", async () => {
    render(<ChangePassword />);
    await userEvent.type(screen.getByLabelText("Current password"), "current passphrase");
    await userEvent.type(screen.getByLabelText("New password"), "new private passphrase");
    await userEvent.type(screen.getByLabelText("Confirm password"), "new private passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(auth.changePassword).toHaveBeenCalledWith("current passphrase", "new private passphrase"));
    expect(auth.clearLocalSession).toHaveBeenCalled();
    expect(auth.replace).toHaveBeenCalledWith("/login");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("shows an incorrect-current-password error without signing out", async () => {
    auth.changePassword.mockRejectedValue(new Error("Your current password is incorrect."));
    render(<ChangePassword />);
    await userEvent.type(screen.getByLabelText("Current password"), "wrong passphrase");
    await userEvent.type(screen.getByLabelText("New password"), "new private passphrase");
    await userEvent.type(screen.getByLabelText("Confirm password"), "new private passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("current password is incorrect");
    expect(auth.clearLocalSession).not.toHaveBeenCalled();
    expect(auth.replace).not.toHaveBeenCalled();
  });
});
