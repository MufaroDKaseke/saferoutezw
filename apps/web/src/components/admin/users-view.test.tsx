import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionUser } from "@/types";
import type { ManagedUser } from "@/lib/api/users";
import { ApiError } from "@/lib/api/errors";
import { getNavGroups } from "@/components/layout/nav-config";
import { UsersView } from "./users-view";

const api = vi.hoisted(() => ({ listUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), revokeUserSessions: vi.fn() }));
const auth = vi.hoisted(() => ({ user: null as SessionUser | null, loading: false, signIn: vi.fn() }));
vi.mock("@/lib/api/users", () => api);
vi.mock("@/hooks/use-demo-session", () => ({ useSession: () => auth }));
vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
vi.mock("@/lib/app-mode", async (original) => ({ ...await original<typeof import("@/lib/app-mode")>(), APP_MODE: "nust_newsroom", isNewsroomMode: true, PRODUCT_NAME: "NUST FM" }));

const account = (id: string, name: string, role: ManagedUser["role"], active = true): ManagedUser => ({
  id, display_name: name, email: `${id}@example.test`, role, is_active: active, created_at: "2026-11-17T08:00:00Z",
});
const admin = account("a1", "Ada Admin", "admin");
const reporter = account("r1", "Rudo Reporter", "reporter");
const password = "a private newsroom passphrase";

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "api");
  auth.loading = false;
  auth.user = { id: admin.id, name: admin.display_name, email: admin.email, role: "admin", title: "Administrator", isDemo: false };
  api.listUsers.mockResolvedValue({ items: [admin, reporter], total: 2, page: 1, page_size: 15 });
  api.createUser.mockResolvedValue(account("n1", "New Producer", "editor"));
  api.updateUser.mockResolvedValue(reporter);
  api.revokeUserSessions.mockResolvedValue({ revoked: 2 });
});
afterEach(() => vi.unstubAllEnvs());

describe("Users & roles", () => {
  it.each(["reporter", "editor", "analyst"] as const)("does not fetch user data for %s", (role) => {
    auth.user!.role = role;
    render(<UsersView />);
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(api.listUsers).not.toHaveBeenCalled();
    expect(getNavGroups("nust_newsroom", role).flatMap((g) => g.items).some((i) => i.href === "/users")).toBe(false);
  });

  it("shows the admin navigation, user list and account actions", async () => {
    render(<UsersView />);
    expect(await screen.findByText("Rudo Reporter")).toBeInTheDocument();
    expect(getNavGroups("nust_newsroom", "admin").flatMap((g) => g.items).some((i) => i.href === "/users")).toBe(true);
    expect(screen.getByRole("button", { name: "Add user" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Change password" })).toHaveAttribute("href", "/settings#password");
  });

  it("creates an account with a newsroom role and matching initial password", async () => {
    render(<UsersView />);
    await userEvent.click(screen.getByRole("button", { name: "Add user" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "New Producer");
    await userEvent.type(within(dialog).getByLabelText("Email"), "new@example.test");
    expect(within(dialog).getAllByRole("option")).toHaveLength(4);
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "editor");
    await userEvent.type(within(dialog).getByLabelText("Initial password"), password);
    await userEvent.type(within(dialog).getByLabelText("Confirm password"), password);
    await userEvent.click(within(dialog).getByRole("button", { name: "Create user" }));
    await waitFor(() => expect(api.createUser).toHaveBeenCalledWith({ email: "new@example.test", display_name: "New Producer", role: "editor", password }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("edits another user's role and deactivates their account", async () => {
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Rudo Reporter" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "editor");
    await userEvent.click(within(dialog).getByRole("switch", { name: "Account active" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.updateUser).toHaveBeenCalledWith("r1", { display_name: "Rudo Reporter", role: "editor", is_active: false }));
  });

  it("requires an email address accepted by the sign-in screen", async () => {
    render(<UsersView />);
    await userEvent.click(screen.getByRole("button", { name: "Add user" }));
    await userEvent.type(screen.getByLabelText("Name"), "New User");
    await userEvent.type(screen.getByLabelText("Email"), "new@newsroom");
    await userEvent.click(screen.getByRole("button", { name: "Create user" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a full email address");
    expect(api.createUser).not.toHaveBeenCalled();
  });

  it("prevents changing your own Administrator role or deactivating yourself", async () => {
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Ada Admin" }));
    expect(screen.getByLabelText("Role", { selector: "select" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Account active" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Reset password for Ada Admin" })).not.toBeInTheDocument();
  });

  it("validates password confirmation, resets only the password, and discards it on close", async () => {
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "Reset password for Rudo Reporter" }));
    await userEvent.type(screen.getByLabelText("New password"), password);
    await userEvent.type(screen.getByLabelText("Confirm password"), "different password");
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(api.updateUser).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByLabelText("Confirm password"));
    await userEvent.type(screen.getByLabelText("Confirm password"), password);
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(api.updateUser).toHaveBeenCalledWith("r1", { password }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Reset password for Rudo Reporter" }));
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("keeps a rejected account edit open with the server's error", async () => {
    api.updateUser.mockRejectedValue(new ApiError("This account cannot be changed.", 409));
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Rudo Reporter" }));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This account cannot be changed.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("filters through the server and resets pagination when searching", async () => {
    api.listUsers.mockResolvedValue({ items: [admin, reporter], total: 31, page: 1, page_size: 15 });
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    await userEvent.type(screen.getByLabelText("Search users"), "Rudo");
    await waitFor(() => expect(api.listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, q: "Rudo" })));
    await userEvent.click(screen.getByRole("combobox", { name: "Role" }));
    await userEvent.click(screen.getByRole("option", { name: "Reporter" }));
    await waitFor(() => expect(api.listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ q: "Rudo", role: "reporter" })));
  });

  it("ends another user's sessions after the administrator confirms", async () => {
    render(<UsersView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Rudo Reporter" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "End all sign-in sessions" }));
    expect(api.revokeUserSessions).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "End sessions" }));
    await waitFor(() => expect(api.revokeUserSessions).toHaveBeenCalledWith("r1"));
  });
});
