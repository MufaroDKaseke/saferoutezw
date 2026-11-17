import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm, validateLogin } from "./login-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/login" }));

const mode = vi.hoisted(() => ({ newsroom: false }));
vi.mock("@/lib/app-mode", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/app-mode")>(),
  get isNewsroomMode() { return mode.newsroom; },
  get PRODUCT_NAME() { return mode.newsroom ? "NUST FM" : "SafeRouteZW"; },
}));

beforeEach(() => {
  mode.newsroom = false;
  push.mockClear();
  window.localStorage.clear();
});

describe("login branding", () => {
  it("uses the station logo and newsroom copy in NUST FM mode", () => {
    mode.newsroom = true;
    render(<LoginForm />);
    expect(screen.getByRole("heading", { level: 1, name: "Sign in to NUST FM" })).toBeInTheDocument();
    const logos = screen.getAllByRole("img", { name: "NUST FM 101.1 — Feel the vibe!" });
    expect(logos).toHaveLength(2);
    for (const logo of logos) expect(logo).toHaveAttribute("src", expect.stringContaining("nust-fm-logo.jpg"));
    expect(screen.getByText("The NUST FM newsroom")).toBeInTheDocument();
    expect(screen.queryByText(/road safety intelligence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SafeRouteZW turns road reports/)).not.toBeInTheDocument();
  });

  it("keeps the road-safety login in SafeRouteZW mode", () => {
    render(<LoginForm />);
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText(/SafeRouteZW turns road reports/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /NUST FM/ })).not.toBeInTheDocument();
  });
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
