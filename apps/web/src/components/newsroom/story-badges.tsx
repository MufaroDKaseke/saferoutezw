import { Check, CircleDashed, CornerUpLeft, Hourglass, PencilLine, Radio, ShieldAlert, Sparkles, X, type LucideIcon } from "lucide-react";
import { Chip, type Tone } from "@/components/shared/status";
import { STORY_STAGE_LABEL, type ScriptOrigin, type StoryStage } from "@/lib/newsroom/taxonomy";

/**
 * Colour carries meaning but never stands alone: every chip has an icon and a word.
 * amber = waiting on a person, emerald = approved or aired, indigo = machine-made, slate = neutral.
 */
const STAGE: Record<StoryStage, { tone: Tone; icon: LucideIcon }> = {
  assigned: { tone: "slate", icon: CircleDashed },
  drafting: { tone: "amber", icon: PencilLine },
  changes_requested: { tone: "amber", icon: CornerUpLeft },
  in_review: { tone: "amber", icon: Hourglass },
  approved: { tone: "emerald", icon: Check },
  broadcast: { tone: "emerald", icon: Radio },
  dropped: { tone: "slate", icon: X },
};

export function StoryStageBadge({ stage }: { stage: StoryStage }) {
  const { tone, icon } = STAGE[stage];
  return (
    <Chip tone={tone} icon={icon}>
      {STORY_STAGE_LABEL[stage]}
    </Chip>
  );
}

/** Only machine-written versions are marked. A person's edit of a draft is a normal version. */
export function ScriptOriginBadge({ origin }: { origin: ScriptOrigin }) {
  if (origin !== "ai_draft") return null;
  return (
    <Chip tone="indigo" icon={Sparkles}>
      AI draft
    </Chip>
  );
}

/** The Executive Producer approved a script they wrote (or a story assigned to them). Allowed, but visible. */
export function SelfApprovedBadge() {
  return (
    <Chip tone="amber" icon={ShieldAlert}>
      Self-approved
    </Chip>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <Chip tone="emerald" icon={Check}>
      Verified
    </Chip>
  ) : (
    <Chip tone="slate" icon={CircleDashed}>
      Not verified
    </Chip>
  );
}
