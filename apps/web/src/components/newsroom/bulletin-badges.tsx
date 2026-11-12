import { Check, CircleDashed, Hourglass, PencilLine, Radio, X, type LucideIcon } from "lucide-react";
import { Chip, type Tone } from "@/components/shared/status";
import type { RevisionState } from "@/lib/newsroom/types";

const STATE: Record<RevisionState, { label: string; tone: Tone; icon: LucideIcon }> = {
  draft: { label: "Draft", tone: "slate", icon: PencilLine },
  pending_approval: { label: "Awaiting approval", tone: "amber", icon: Hourglass },
  approved: { label: "Approved", tone: "emerald", icon: Check },
  superseded: { label: "Superseded", tone: "slate", icon: CircleDashed },
  rejected: { label: "Rejected", tone: "red", icon: X },
};

export const REVISION_STATE_LABEL: Record<RevisionState, string> = {
  draft: STATE.draft.label,
  pending_approval: STATE.pending_approval.label,
  approved: STATE.approved.label,
  superseded: STATE.superseded.label,
  rejected: STATE.rejected.label,
};

export function RevisionStateBadge({ state }: { state: RevisionState }) {
  const { label, tone, icon } = STATE[state];
  return (
    <Chip tone={tone} icon={icon}>
      {label}
    </Chip>
  );
}

export function AiredBadge() {
  return (
    <Chip tone="emerald" icon={Radio}>
      Broadcast
    </Chip>
  );
}
