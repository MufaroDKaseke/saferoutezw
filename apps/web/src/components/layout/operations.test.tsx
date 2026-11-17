import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionUser } from "@/types";
import ProcessingPage from "@/app/(dashboard)/processing/page";
import SourcesPage from "@/app/(dashboard)/sources/page";
import SettingsPage from "@/app/(dashboard)/settings/page";
import { AccountView } from "@/components/auth/account-view";
import { getNavGroups } from "./nav-config";
import { UserMenu } from "./user-menu";

const auth = vi.hoisted(() => ({ user: null as SessionUser | null, loading: false, signOut: vi.fn() }));
const api = vi.hoisted(() => ({ getBacklog: vi.fn(), listProcessing: vi.fn(), listSources: vi.fn() }));
vi.mock("@/hooks/use-demo-session", () => ({ useSession: () => auth, useDemoSession: () => auth, clearLocalSession: vi.fn() }));
vi.mock("@/lib/app-mode", async (original) => ({ ...await original<typeof import("@/lib/app-mode")>(), APP_MODE: "nust_newsroom", isNewsroomMode: true }));
vi.mock("@/lib/api/processing", () => ({ ...api, retryJob: vi.fn() }));
vi.mock("@/lib/api/sources", () => ({ listSources: api.listSources, listIngestionHistory: vi.fn(), createSource: vi.fn(), updateSource: vi.fn(), testSource: vi.fn(), triggerPoll: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "api");
  auth.user = { id: "ep", name: "Esther Producer", email: "ep@example.test", role: "editor", title: "Executive Producer", isDemo: false };
  api.getBacklog.mockResolvedValue({ awaitingScreening: 1, awaitingFullText: 2, awaitingExtraction: 3, failedNeedingAttention: 0 });
  api.listSources.mockResolvedValue([]);
  api.listProcessing.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 });
});
afterEach(() => vi.unstubAllEnvs());

describe("newsroom Operations access", () => {
  it.each([ProcessingPage, SourcesPage, SettingsPage])("blocks a direct Operations page visit without loading its data", (Page) => {
    render(<Page />);
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(api.getBacklog).not.toHaveBeenCalled();
    expect(api.listProcessing).not.toHaveBeenCalled();
    expect(api.listSources).not.toHaveBeenCalled();
  });

  it("hides the Operations group for producers while retaining the full group for admins", () => {
    expect(getNavGroups("nust_newsroom", "editor").some((g) => g.label === "Operations")).toBe(false);
    expect(getNavGroups("nust_newsroom", "admin").find((g) => g.label === "Operations")?.items.map((i) => i.href))
      .toEqual(["/sources", "/processing", "/settings", "/users"]);
    expect(getNavGroups("road_safety", "editor").some((g) => g.label === "Operations")).toBe(true);
  });

  it("keeps the producer's profile link and removes Settings from the account menu", async () => {
    render(<UserMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Account menu for Esther Producer" }));
    expect(screen.getByRole("menuitem", { name: "User profile" })).toHaveAttribute("href", "/account");
    expect(screen.queryByRole("menuitem", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("keeps profile and personal password controls available to the producer", () => {
    render(<AccountView />);
    expect(screen.getByRole("heading", { name: "Your account" })).toBeInTheDocument();
    expect(screen.getByText("Executive Producer")).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change password" })).toBeInTheDocument();
  });

  it("loads the processing page for an Administrator with newsroom stage labels", async () => {
    auth.user!.role = "admin";
    render(<ProcessingPage />);
    expect(await screen.findByText("Awaiting preparation")).toBeInTheDocument();
    expect(screen.getByText("Awaiting AI classification")).toBeInTheDocument();
    expect(api.listProcessing).toHaveBeenCalled();
    expect(screen.queryByText("This could not be loaded")).not.toBeInTheDocument();
  });
});
