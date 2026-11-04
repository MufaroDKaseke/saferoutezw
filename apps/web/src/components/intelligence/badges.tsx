import { Activity, BookOpen, Check, CircleDashed, FileBarChart, Hourglass, Megaphone, Newspaper, X, type LucideIcon } from "lucide-react";
import { Chip, type Tone } from "@/components/shared/status";
import {
  CLASSIFICATION_STATUS_LABEL,
  RECORD_STATUS_LABEL,
  categoryLabel,
  geographicScopeLabel,
  recordKindLabel,
  subtypeLabel,
} from "@/lib/domain/intelligence";
import type { RecordKind, RecordStatus } from "@/lib/taxonomy.generated";
import type { ClassificationStatus } from "@/types";

/** Neutral chip for a category: the label is the signal, colour is never. */
export function CategoryBadge({ category, subtype }: { category: string; subtype?: string | null }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5">
      <Chip tone="slate">{categoryLabel(category)}</Chip>
      {subtype ? <span className="text-xs text-slate-600">{subtypeLabel(subtype)}</span> : null}
    </span>
  );
}

const KIND_STYLE: Record<RecordKind, { tone: Tone; icon: LucideIcon }> = {
  actionable_event: { tone: "amber", icon: Activity },
  informational_development: { tone: "slate", icon: Newspaper },
  statistical_report: { tone: "indigo", icon: FileBarChart },
  research_or_analysis: { tone: "indigo", icon: BookOpen },
  advisory: { tone: "amber", icon: Megaphone },
  unknown: { tone: "slate", icon: CircleDashed },
};

/** Whether a record describes a specific event or is background information. */
export function RecordKindBadge({ kind }: { kind: RecordKind | string }) {
  const style = KIND_STYLE[kind as RecordKind] ?? KIND_STYLE.unknown;
  return (
    <Chip tone={style.tone} icon={style.icon}>
      {recordKindLabel(kind)}
    </Chip>
  );
}

const STATUS_TONE: Record<RecordStatus, { tone: Tone; icon: LucideIcon }> = {
  candidate: { tone: "indigo", icon: Hourglass },
  under_review: { tone: "amber", icon: Hourglass },
  approved: { tone: "emerald", icon: Check },
  published: { tone: "emerald", icon: Check },
  rejected: { tone: "slate", icon: X },
  archived: { tone: "slate", icon: X },
};

export function RecordStatusBadge({ status }: { status: RecordStatus | string }) {
  const style = STATUS_TONE[status as RecordStatus] ?? STATUS_TONE.candidate;
  return (
    <Chip tone={style.tone} icon={style.icon}>
      {RECORD_STATUS_LABEL[status as RecordStatus] ?? status}
    </Chip>
  );
}

const CLASSIFICATION_TONE: Record<ClassificationStatus, Tone> = {
  classified: "indigo",
  awaiting_classification: "amber",
  unscreened: "slate",
  filtered: "slate",
  not_relevant: "slate",
  failed: "red",
};

/** Classification state of a news item. "Classified" is an AI suggestion until an editor approves it. */
export function ClassificationStatusBadge({ status }: { status: ClassificationStatus }) {
  return <Chip tone={CLASSIFICATION_TONE[status]}>{CLASSIFICATION_STATUS_LABEL[status]}</Chip>;
}

export function ScopeText({ scope }: { scope: string | null | undefined }) {
  return <span className="text-xs text-slate-600">Scope: {geographicScopeLabel(scope)}</span>;
}
