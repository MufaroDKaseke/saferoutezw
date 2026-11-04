"use client";

import { useState } from "react";
import { AlertTriangle, Check, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SimulationNote } from "@/components/shared/notes";
import { Chip } from "@/components/shared/status";
import { getDataMode } from "@/lib/api/config";
import { hasBlockingCheck, type BulletinCheck } from "@/lib/domain/bulletin-checks";
import { INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import type { IncidentType } from "@/types";

/* ---------------------------------------------------------------- approve */

export interface ApproveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  referenceCode: string;
  incidentType: IncidentType;
  headline: string;
  body: string;
  /** "Bulletin version 2 · edited by Tendai Moyo" */
  versionLabel: string;
  checks: BulletinCheck[];
  pending: boolean;
  onConfirm: () => void;
}

const CHECK_STYLE = {
  block: { tone: "red" as const, label: "Fix first", icon: ShieldAlert },
  warning: { tone: "amber" as const, label: "Warning", icon: AlertTriangle },
  checked: { tone: "emerald" as const, label: "Checked", icon: Check },
};

/**
 * Approval is always an explicit act on exact text. The dialog shows the bulletin
 * that would be approved, runs the wording checks, and states honestly what the
 * button will and will not do.
 */
export function ApproveDialog({
  open,
  onOpenChange,
  referenceCode,
  incidentType,
  headline,
  body,
  versionLabel,
  checks,
  pending,
  onConfirm,
}: ApproveDialogProps) {
  const blocked = hasBlockingCheck(checks);
  const mock = getDataMode() === "mock";
  return (
    <Dialog open={open} onOpenChange={(next) => (!pending ? onOpenChange(next) : undefined)}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">Approve this exact bulletin?</DialogTitle>
          <DialogDescription>
            This is the version that would be approved. Later edits create a new version that needs fresh approval.
          </DialogDescription>
        </DialogHeader>

        <article className="rounded-xl border bg-slate-50 p-4" aria-label="Bulletin to approve">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-slate-600">
            <span>
              {referenceCode} · {INCIDENT_TYPE_LABEL[incidentType]}
            </span>
            <span>{versionLabel}</span>
          </div>
          <h3 className="text-base leading-snug font-bold">{headline}</h3>
          <p className="mt-2 text-sm leading-relaxed whitespace-pre-line">{body}</p>
        </article>

        <ul className="space-y-2" aria-label="Wording checks">
          {checks.map((c) => {
            const s = CHECK_STYLE[c.level];
            return (
              <li key={`${c.id}-${c.level}`} className="flex items-start gap-2.5 text-sm">
                <Chip tone={s.tone} icon={s.icon} className="mt-0.5">
                  {s.label}
                </Chip>
                <span className="leading-snug">{c.text}</span>
              </li>
            );
          })}
        </ul>

        {mock ? (
          <SimulationNote>
            <strong>Simulation only.</strong> Confirming records a mock approval. Nothing is published or sent to
            WhatsApp, SMS or any API.
          </SimulationNote>
        ) : (
          <SimulationNote>
            Confirming records your approval of this exact version. Publishing to channels is a separate step.
          </SimulationNote>
        )}

        <DialogFooter>
          <Button variant="outline" size="lg" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="approve" size="lg" onClick={onConfirm} disabled={pending || blocked}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {mock ? "Confirm approval (simulated)" : "Confirm approval"}
          </Button>
        </DialogFooter>
        {blocked ? (
          <p role="alert" className="text-xs font-medium text-red-700">
            Approval is disabled until the wording problem above is fixed.
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------- reason-required dialogs */

interface ReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  label: string;
  placeholder: string;
  /** Minimum characters, enforced here and again by the data layer. */
  minLength: number;
  confirmLabel: string;
  confirmVariant: "reject" | "default";
  pending: boolean;
  serverError?: string | null;
  onConfirm: (reason: string) => void;
}

function ReasonDialog(props: ReasonDialogProps) {
  const { open, onOpenChange, pending } = props;
  return (
    <Dialog open={open} onOpenChange={(next) => (!pending ? onOpenChange(next) : undefined)}>
      {open ? <ReasonBody {...props} /> : null}
    </Dialog>
  );
}

function ReasonBody({
  onOpenChange,
  title,
  description,
  label,
  placeholder,
  minLength,
  confirmLabel,
  confirmVariant,
  pending,
  serverError,
  onConfirm,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const tooShort = reason.trim().length < minLength;
  const message = touched && tooShort ? `Write at least ${minLength} characters so the next editor understands why.` : serverError;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!tooShort) onConfirm(reason.trim());
  };

  return (
    <DialogContent className="sm:max-w-lg">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="decision-reason">{label}</Label>
          <Textarea
            id="decision-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
            placeholder={placeholder}
            aria-invalid={!!message}
            aria-describedby={message ? "decision-reason-error" : undefined}
            autoFocus
          />
          {message ? (
            <p id="decision-reason-error" role="alert" className="text-xs font-medium text-red-700">
              {message}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" size="lg" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" variant={confirmVariant} size="lg" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

export function RejectDialog(props: Pick<ReasonDialogProps, "open" | "onOpenChange" | "pending" | "serverError" | "onConfirm">) {
  return (
    <ReasonDialog
      {...props}
      title="Reject this report?"
      description="The reason is saved in the review history. It is never shown to the public."
      label="Reason for rejecting"
      placeholder="e.g. Describes a crash from three weeks ago, not a current incident."
      minLength={10}
      confirmLabel="Reject report"
      confirmVariant="reject"
    />
  );
}

export function RequestChangesDialog(
  props: Pick<ReasonDialogProps, "open" | "onOpenChange" | "pending" | "serverError" | "onConfirm">,
) {
  return (
    <ReasonDialog
      {...props}
      title="Request changes"
      description="Say what needs to change. The report stays in the queue as “Needs changes”."
      label="What needs to change?"
      placeholder="e.g. The source does not say the truck was gutted. Reword and confirm the location."
      minLength={5}
      confirmLabel="Request changes"
      confirmVariant="default"
    />
  );
}
