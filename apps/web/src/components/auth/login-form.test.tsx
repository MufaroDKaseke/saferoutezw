import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm, validateLogin } from "./login-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/login" }));

beforeEach(() => {
  push.mockClear();
  window.localStorage.clear();
});

describe("validateLogin", () => {
  it("asks for both fields", () => {
    expect(validateLogin("", "")).toEqual({ email: "Enter your email address.", password: "Enter your password." });
  });
  it("rejects a malformed email", () => {
    expect(validateLogin("not-an-email", "x").email).toMatch(/full email address/);
  });
  it("accepts well-formed input", () => {
    expect(validateLogin("editor@example.com", "secret")).toEqual({});
  });
});

describe("LoginForm (demo mode)", () => {
  it("says plainly that this is a demo session and checks no credentials", () => {
    render(<LoginForm />);
    expect(screen.getByText(/no real authentication yet/i)).toBeInTheDocument();
  });

  it("shows inline errors and does not sign in when invalid", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(screen.getByRole("button", { name: /Sign in to the demo/ }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
  });

  it("opens the demo and goes to the dashboard with valid input", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText("Email"), "editor@example.com");
    await user.type(screen.getByLabelText("Password"), "anything");
    await user.click(screen.getByRole("button", { name: /Sign in to the demo/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"));
  });
});
