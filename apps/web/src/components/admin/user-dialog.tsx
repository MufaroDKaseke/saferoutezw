"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PasswordFields, passwordProblem } from "@/components/auth/password-fields";
import { createUser, updateUser, type ManagedUser } from "@/lib/api/users";
import { errorMessage } from "@/lib/api/errors";
import { isNewsroomMode } from "@/lib/app-mode";
import { roleTitle } from "@/lib/newsroom/roles";
import type { UserRole } from "@/types";

export const MANAGED_ROLES: readonly UserRole[] = isNewsroomMode
  ? ["reporter", "editor", "analyst", "admin"]
  : ["editor", "analyst", "admin", "reporter", "contributor", "service"];

const ROLE_HELP: Record<UserRole, string> = {
  reporter: "Writes and submits their own stories. Cannot approve scripts or bulletins.",
  editor: isNewsroomMode ? "Assigns stories, approves scripts and manages bulletins across the newsroom." : "Reviews and approves editorial work.",
  analyst: "Read-only access to the newsroom.",
  admin: "Full editorial access, plus user accounts, roles and settings.",
  contributor: "Legacy contributor role. No newsroom access.",
  service: "Automation account. Cannot approve work or access the newsroom.",
};

/** Mounted only while open, so closing always discards password fields. */
export function UserDialog({ target, resetPassword = false, self, onClose, onSaved }: {
  target?: ManagedUser; resetPassword?: boolean; self: boolean;
  onClose: () => void; onSaved: (user: ManagedUser) => void;
}) {
  const [name, setName] = useState(target?.display_name ?? "");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>(target?.role ?? (isNewsroomMode ? "reporter" : "analyst"));
  const [active, setActive] = useState(target?.is_active ?? true);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const title = resetPassword ? "Reset password" : target ? "Edit user" : "Add user";
  const roles = MANAGED_ROLES.includes(role) ? MANAGED_ROLES : [role, ...MANAGED_ROLES];

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!resetPassword && !name.trim()) { setError("Enter a name."); return; }
    if (!target && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) { setError("Enter a full email address, such as name@example.com."); return; }
    const problem = resetPassword || !target
      ? passwordProblem(password, confirmation) : null;
    if (problem) { setError(problem); return; }
    setPending(true); setError(null);
    try {
      const saved = target
        ? await updateUser(target.id, resetPassword ? { password } : {
            display_name: name.trim(),
            ...(role !== target.role ? { role } : {}),
            ...(active !== target.is_active ? { is_active: active } : {}),
          })
        : await createUser({ email: email.trim(), display_name: name.trim(), role, password });
      setPassword(""); setConfirmation("");
      toast.success(resetPassword ? "Password reset. Share the new password securely with the user." : target ? "User updated." : "User created. Share their initial password securely.");
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg" showCloseButton={!pending}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{target ? `${target.display_name} · ${target.email}` : "Create a personal account for a member of your team."}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-5" noValidate>
          {!resetPassword ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="user-name">Name</Label>
                <Input id="user-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} disabled={pending} autoComplete="off" required />
              </div>
              {!target ? (
                <div className="space-y-1.5">
                  <Label htmlFor="user-email">Email</Label>
                  <Input id="user-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} disabled={pending} autoComplete="off" required />
                </div>
              ) : null}
              <div className="space-y-1.5">
                <Label htmlFor="user-role">Role</Label>
                <select id="user-role" value={role} onChange={(e) => setRole(e.target.value as UserRole)} disabled={pending || self}
                  className="h-10 w-full rounded-lg border border-input bg-white px-3 text-sm" aria-describedby="user-role-help">
                  {roles.map((value) => <option key={value} value={value}>{roleTitle(value)}</option>)}
                </select>
                <p id="user-role-help" className="text-xs leading-relaxed text-slate-600">{self ? "Your own Administrator role cannot be changed here." : ROLE_HELP[role]}</p>
              </div>
              {target ? (
                <div className="flex items-start justify-between gap-5 rounded-lg border p-3">
                  <div>
                    <Label htmlFor="user-active">Account active</Label>
                    <p className="mt-1 text-xs text-slate-600">{self ? "Your own account must remain active." : "Inactive users cannot sign in. Their work stays in the archive."}</p>
                  </div>
                  <Switch id="user-active" checked={active} onCheckedChange={setActive} disabled={pending || self} />
                </div>
              ) : null}
            </>
          ) : null}
          {!target || resetPassword ? (
            <>
              <PasswordFields password={password} confirmation={confirmation} onPassword={setPassword} onConfirmation={setConfirmation}
                disabled={pending} label={target ? "New password" : "Initial password"} />
              <p className="text-xs leading-relaxed text-slate-600">{target ? "Existing sign-in sessions will end. " : ""}Share the password securely with the user. They can change it in Account preferences after signing in.</p>
              {target && !target.is_active ? <p className="text-xs text-amber-800">This account is inactive. Resetting its password will keep it inactive.</p> : null}
            </>
          ) : <p className="text-xs text-slate-600">Changing a role or deactivating an account signs that user out on all devices.</p>}
          {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>Cancel</Button>
            <Button type="submit" disabled={pending}>{pending ? "Saving…" : resetPassword ? "Reset password" : target ? "Save changes" : "Create user"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
