"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { changePassword } from "@/lib/api/auth";
import { errorMessage } from "@/lib/api/errors";
import { clearLocalSession } from "@/hooks/use-demo-session";
import { PasswordFields, passwordProblem } from "./password-fields";

export function ChangePassword() {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const problem = !current ? "Enter your current password." : passwordProblem(password, confirmation);
    setError(problem);
    if (problem) return;
    setPending(true);
    try {
      await changePassword(current, password);
      setCurrent(""); setPassword(""); setConfirmation("");
      toast.success("Password changed. Sign in with your new password.");
      clearLocalSession();
      router.replace("/login");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={submit} className="max-w-md space-y-4" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="current-password">Current password</Label>
        <Input id="current-password" type="password" autoComplete="current-password" value={current}
          onChange={(e) => setCurrent(e.target.value)} disabled={pending} required />
      </div>
      <PasswordFields password={password} confirmation={confirmation} onPassword={setPassword} onConfirmation={setConfirmation} disabled={pending} />
      <p className="text-xs leading-relaxed text-slate-600">Changing your password signs you out on all devices. You will sign in again with the new password.</p>
      {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
      <Button type="submit" disabled={pending}>{pending ? "Changing password…" : "Change password"}</Button>
    </form>
  );
}
