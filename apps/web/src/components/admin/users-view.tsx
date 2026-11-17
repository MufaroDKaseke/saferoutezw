"use client";

import Link from "next/link";
import { useState } from "react";
import { KeyRound, LogOut, MoreHorizontal, Plus, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/shared/page-header";
import { FilterBar, SearchField, SelectField } from "@/components/shared/filters";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Chip } from "@/components/shared/status";
import { EmptyState, QueryError, TableSkeleton } from "@/components/shared/states";
import { useSession } from "@/hooks/use-demo-session";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { listUsers, revokeUserSessions, type ManagedUser } from "@/lib/api/users";
import { errorMessage } from "@/lib/api/errors";
import { roleTitle } from "@/lib/newsroom/roles";
import { formatShort } from "@/lib/formatters/date";
import type { SessionUser, UserRole } from "@/types";
import { MANAGED_ROLES, UserDialog } from "./user-dialog";

export function UsersView() {
  const { user, loading, signIn } = useSession();
  if (loading) return <TableSkeleton rows={5} cols={4} />;
  if (user?.role !== "admin") {
    return <EmptyState icon={ShieldCheck} title="Administrator access required" description="Only Administrators can manage user accounts and roles." />;
  }
  if (user.isDemo || getDataMode() === "mock") {
    return <EmptyState title="Sign in to manage real users" description="User administration is available with a live Administrator account." />;
  }
  return <UserManagement actor={user} onSelfChanged={(saved) => signIn({ ...user, name: saved.display_name, role: saved.role, title: roleTitle(saved.role) })} />;
}

function UserManagement({ actor, onSelfChanged }: { actor: SessionUser; onSelfChanged: (user: ManagedUser) => void }) {
  const list = useListState({ search: "", role: undefined as UserRole | undefined, status: undefined as "active" | "inactive" | undefined });
  const { filters, page, setPage } = list;
  const search = useDebouncedValue(filters.search);
  const query = { page, q: search || undefined, role: filters.role, isActive: filters.status === undefined ? undefined : filters.status === "active" };
  const users = useResource(`admin:users:${JSON.stringify(query)}`, () => listUsers(query));
  const [dialog, setDialog] = useState<{ target?: ManagedUser; resetPassword?: boolean } | null>(null);
  const [revoke, setRevoke] = useState<ManagedUser | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const data = users.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  const saved = (user: ManagedUser) => {
    if (user.id === actor.id) onSelfChanged(user);
    users.refetch();
  };
  const endSessions = async () => {
    if (!revoke) return;
    setRevoking(true); setRevokeError(null);
    try {
      await revokeUserSessions(revoke.id);
      toast.success(`Sign-in sessions ended for ${revoke.display_name}.`);
      setRevoke(null);
    } catch (e) {
      setRevokeError(errorMessage(e));
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Users & roles" description="Manage your team's accounts, access and passwords."
        actions={<Button onClick={() => setDialog({})}><Plus aria-hidden /> Add user</Button>} />
      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search users" placeholder="Name or email" value={filters.search} onChange={(v) => list.setFilter("search", v)} />
        <SelectField label="Role" value={filters.role} onChange={(v) => list.setFilter("role", v)}
          options={MANAGED_ROLES.map((value) => ({ value, label: roleTitle(value) }))} allLabel="All roles" />
        <SelectField label="Access" value={filters.status} onChange={(v) => list.setFilter("status", v)}
          options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]} allLabel="All accounts" />
      </FilterBar>

      {users.error ? <QueryError error={users.error} onRetry={users.refetch} what="users" /> : !data ? (
        <TableSkeleton rows={5} cols={4} />
      ) : data.items.length === 0 ? (
        <EmptyState title="No users match these filters" description="Try another name, email or role, or clear the filters." />
      ) : (
        <div className="overflow-x-auto rounded-xl bg-card ring-1 ring-foreground/10" aria-busy={users.isFetching}>
          <table className="w-full min-w-[780px] text-sm">
            <caption className="sr-only">User accounts, roles and access</caption>
            <thead className="border-b bg-slate-50 text-left text-xs text-slate-600">
              <tr>{["User", "Role", "Access", "Joined", "Actions"].map((label) => <th key={label} scope="col" className="px-4 py-3 font-semibold">{label}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((u) => {
                const self = u.id === actor.id;
                return (
                  <tr key={u.id}>
                    <th scope="row" className="px-4 py-4 text-left font-normal">
                      <span className="font-semibold">{u.display_name}</span>{self ? <span className="ml-2 text-xs text-slate-500">You</span> : null}
                      <span className="mt-1 block text-xs text-slate-600">{u.email}</span>
                    </th>
                    <td className="px-4 py-4"><Chip tone={u.role === "admin" ? "indigo" : "slate"}>{roleTitle(u.role)}</Chip></td>
                    <td className="px-4 py-4"><Chip tone={u.is_active ? "emerald" : "slate"}>{u.is_active ? "Active" : "Inactive"}</Chip></td>
                    <td className="tnum whitespace-nowrap px-4 py-4 text-xs text-slate-600">{formatShort(u.created_at)}</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-1.5">
                        <Button variant="outline" size="sm" onClick={() => setDialog({ target: u })} disabled={users.isFetching} aria-label={`Edit ${u.display_name}`}>Edit</Button>
                        {self ? (
                          <Button asChild variant="ghost" size="sm"><Link href="/account#password">Change password</Link></Button>
                        ) : (
                          <>
                            <Button variant="ghost" size="sm" disabled={users.isFetching} onClick={() => setDialog({ target: u, resetPassword: true })} aria-label={`Reset password for ${u.display_name}`}>
                              <KeyRound aria-hidden /> Reset password
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon-sm" disabled={users.isFetching} aria-label={`More actions for ${u.display_name}`}><MoreHorizontal aria-hidden /></Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onSelect={() => { setRevokeError(null); setRevoke(u); }}><LogOut aria-hidden /> End all sign-in sessions</DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data ? (
        <nav className="flex items-center justify-between gap-4 text-sm text-slate-600" aria-label="User pagination">
          <span>{data.total} users · page {page} of {pages}</span>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1 || users.isFetching} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button variant="outline" disabled={page >= pages || users.isFetching} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </nav>
      ) : null}

      {dialog ? <UserDialog {...dialog} self={dialog.target?.id === actor.id} onClose={() => setDialog(null)} onSaved={saved} /> : null}
      <ConfirmDialog open={!!revoke} onOpenChange={(open) => { if (!open) setRevoke(null); }} title="End all sign-in sessions?"
        description={`${revoke?.display_name ?? "This user"} will need to sign in again on every device. Their account and password stay the same.`}
        confirmLabel="End sessions" onConfirm={endSessions} pending={revoking}>
        {revokeError ? <p role="alert" className="text-sm text-red-700">{revokeError}</p> : null}
      </ConfirmDialog>
    </div>
  );
}
