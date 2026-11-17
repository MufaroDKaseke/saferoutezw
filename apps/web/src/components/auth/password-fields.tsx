"use client";

import { useId, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export function passwordProblem(password: string, confirmation: string): string | null {
  if ([...password].length < 12) return "Use at least 12 characters.";
  if ([...password].length > 256) return "Use at most 256 characters.";
  if (password !== confirmation) return "The passwords do not match.";
  return null;
}

/** Passwords stay in the parent form's memory and are discarded when it closes. */
export function PasswordFields({ password, confirmation, onPassword, onConfirmation, disabled, label = "New password" }: {
  password: string; confirmation: string; onPassword: (value: string) => void;
  onConfirmation: (value: string) => void; disabled?: boolean; label?: string;
}) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-new`}>{label}</Label>
        <Input id={`${id}-new`} type={visible ? "text" : "password"} autoComplete="new-password"
          value={password} onChange={(e) => onPassword(e.target.value)} disabled={disabled} required aria-describedby={`${id}-hint`} />
        <p id={`${id}-hint`} className="text-xs text-slate-600">At least 12 characters. A longer passphrase works well.</p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-confirm`}>Confirm password</Label>
        <Input id={`${id}-confirm`} type={visible ? "text" : "password"} autoComplete="new-password"
          value={confirmation} onChange={(e) => onConfirmation(e.target.value)} disabled={disabled} required />
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={() => setVisible(!visible)} aria-pressed={visible} disabled={disabled}>
        {visible ? "Hide passwords" : "Show passwords"}
      </Button>
    </div>
  );
}
