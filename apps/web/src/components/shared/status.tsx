import {
  AlertTriangle,
  BadgeCheck,
  Check,
  CircleDashed,
  Clock,
  FileText,
  Filter,
  Hourglass,
  Loader2,
  MinusCircle,
  PencilLine,
  Radio,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  ALERT_STATE_LABEL,
  CONNECTION_LABEL,
  EXTRACTION_LABEL,
  JOB_STATUS_LABEL,
  OUTBOX_LABEL,
  PRIORITY_LABEL,
  REVIEW_STATE_LABEL,
  RETRIEVAL_LABEL,
  RISK_LABEL,
  SEVERITY_LABEL,
  VERIFICATION_LABEL,
  VERIFICATION_SHORT_LABEL,
  WORKFLOW_LABEL,
} from "@/lib/formatters/labels";
import type {
  AlertPublicationState,
  ArticleWorkflowState,
  ChannelKind,
  ConnectionStatus,
  ExtractionStatus,
  OutboxStatus,
  PipelineStage,
  ProcessingJobStatus,
  ReviewPriority,
  ReviewState,
  RetrievalStatus,
  RiskLevel,
  Severity,
  VerificationState,
} from "@/types";

/**
 * Status chips. The concept's rule: colour carries meaning, but always paired
 * with an icon and a word, so nothing depends on colour alone.
 *   amber  = pending, unverified, uncertain
 *   emerald = approved, healthy
 *   red    = geographic risk, failure
 *   indigo = anything the AI suggested (never authoritative)
 *   slate  = neutral, rejected, system
 */
export type Tone = "amber" | "emerald" | "red" | "indigo" | "slate";

const TONE: Record<Tone, string> = {
  amber: "bg-amber-100 text-amber-900",
  emerald: "bg-emerald-100 text-emerald-900",
  red: "bg-red-100 text-red-900",
  indigo: "bg-indigo-100 text-indigo-900",
  slate: "bg-slate-100 text-slate-800",
};

export function Chip({
  tone = "slate",
  icon: Icon,
  className,
  children,
}: {
  tone?: Tone;
  icon?: LucideIcon;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] w-fit shrink-0 items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        TONE[tone],
        className,
      )}
    >
      {Icon ? <Icon className="size-3" aria-hidden /> : null}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ review */

const REVIEW_STATE_STYLE: Record<ReviewState, { tone: Tone; icon: LucideIcon }> = {
  pending: { tone: "amber", icon: Clock },
  needs_changes: { tone: "amber", icon: PencilLine },
  approved: { tone: "emerald", icon: Check },
  rejected: { tone: "slate", icon: X },
};

export function ReviewStateBadge({ state }: { state: ReviewState }) {
  const s = REVIEW_STATE_STYLE[state];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {REVIEW_STATE_LABEL[state]}
    </Chip>
  );
}

const PRIORITY_TONE: Record<ReviewPriority, Tone> = { urgent: "red", high: "red", normal: "slate", low: "slate" };

export function PriorityBadge({ priority, short = false }: { priority: ReviewPriority; short?: boolean }) {
  return (
    <Chip tone={PRIORITY_TONE[priority]}>
      {short ? "" : "Priority: "}
      {PRIORITY_LABEL[priority]}
    </Chip>
  );
}

/* ---------------------------------------------------------- severity / risk */

const SEVERITY_TEXT: Record<Severity, string> = {
  fatal: "text-red-800 font-semibold",
  serious: "text-red-700",
  minor: "text-amber-800",
  unknown: "text-slate-600",
};

/** Text-only severity, as in the concept's tables. The word is the signal. */
export function SeverityText({ severity, prefix = true }: { severity: Severity; prefix?: boolean }) {
  return (
    <span className={cn("text-xs", SEVERITY_TEXT[severity])}>
      {prefix ? "Severity: " : ""}
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

const RISK_TONE: Record<RiskLevel, Tone> = { low: "slate", medium: "amber", high: "red", critical: "red" };

export function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) return <span className="text-xs text-muted-foreground">Not assessed</span>;
  return (
    <Chip tone={RISK_TONE[level]} className={level === "critical" ? "font-semibold" : undefined}>
      {RISK_LABEL[level]}
    </Chip>
  );
}

const VERIFICATION_STYLE: Record<VerificationState, { tone: Tone; icon: LucideIcon }> = {
  unverified: { tone: "slate", icon: CircleDashed },
  single_source: { tone: "amber", icon: CircleDashed },
  corroborated: { tone: "amber", icon: Check },
  editor_confirmed: { tone: "emerald", icon: BadgeCheck },
};

export function VerificationBadge({ state, short = false }: { state: VerificationState; short?: boolean }) {
  const s = VERIFICATION_STYLE[state];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {short ? VERIFICATION_SHORT_LABEL[state] : VERIFICATION_LABEL[state]}
    </Chip>
  );
}

/* ----------------------------------------------------------------- AI marks */

/** Everything the AI produced is marked indigo and labelled as a suggestion. */
export function AiBadge({ children = "AI suggestion" }: { children?: React.ReactNode }) {
  return (
    <Chip tone="indigo" icon={Sparkles}>
      {children}
    </Chip>
  );
}

export function SyntheticBadge({ className }: { className?: string }) {
  return (
    <Chip tone="amber" className={cn("h-5 px-1.5 text-[11px]", className)}>
      Demo
    </Chip>
  );
}

/* ---------------------------------------------------------------- articles */

const WORKFLOW_STYLE: Record<ArticleWorkflowState, { tone: Tone; icon: LucideIcon }> = {
  new: { tone: "slate", icon: CircleDashed },
  filtered: { tone: "slate", icon: Filter },
  relevant: { tone: "slate", icon: FileText },
  awaiting_full_text: { tone: "amber", icon: Hourglass },
  full_text_retrieved: { tone: "slate", icon: FileText },
  extraction_pending: { tone: "indigo", icon: Sparkles },
  processed: { tone: "indigo", icon: Sparkles },
  failed: { tone: "red", icon: AlertTriangle },
};

export function WorkflowBadge({ state }: { state: ArticleWorkflowState }) {
  const s = WORKFLOW_STYLE[state];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {WORKFLOW_LABEL[state]}
    </Chip>
  );
}

const RETRIEVAL_STYLE: Record<RetrievalStatus, { tone: Tone; icon: LucideIcon }> = {
  retrieved: { tone: "slate", icon: Check },
  pending: { tone: "amber", icon: Hourglass },
  failed: { tone: "red", icon: AlertTriangle },
  skipped: { tone: "slate", icon: MinusCircle },
};

export function RetrievalBadge({ status }: { status: RetrievalStatus }) {
  const s = RETRIEVAL_STYLE[status];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {RETRIEVAL_LABEL[status]}
    </Chip>
  );
}

const EXTRACTION_STYLE: Record<ExtractionStatus | "not_started", { tone: Tone; icon: LucideIcon }> = {
  not_started: { tone: "slate", icon: MinusCircle },
  pending: { tone: "indigo", icon: Hourglass },
  succeeded: { tone: "indigo", icon: Sparkles },
  failed: { tone: "red", icon: AlertTriangle },
};

export function ExtractionBadge({ status }: { status: ExtractionStatus | "not_started" }) {
  const s = EXTRACTION_STYLE[status];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {EXTRACTION_LABEL[status]}
    </Chip>
  );
}

/* ------------------------------------------------------------------ alerts */

const ALERT_STYLE: Record<AlertPublicationState, { tone: Tone; icon: LucideIcon }> = {
  approved_not_published: { tone: "emerald", icon: BadgeCheck },
  publication_pending: { tone: "amber", icon: Clock },
  published: { tone: "emerald", icon: Check },
  delivery_failed: { tone: "red", icon: AlertTriangle },
  withdrawn: { tone: "slate", icon: X },
};

export function AlertStateBadge({ state }: { state: AlertPublicationState }) {
  const s = ALERT_STYLE[state];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {ALERT_STATE_LABEL[state]}
    </Chip>
  );
}

const OUTBOX_STYLE: Record<OutboxStatus, { tone: Tone; icon: LucideIcon }> = {
  sent: { tone: "emerald", icon: Check },
  failed: { tone: "red", icon: AlertTriangle },
  pending: { tone: "amber", icon: Clock },
  sending: { tone: "amber", icon: Loader2 },
  cancelled: { tone: "slate", icon: X },
};

export function ChannelStatusBadge({ status, channel }: { status: OutboxStatus; channel?: ChannelKind }) {
  const s = OUTBOX_STYLE[status];
  // The public map and API is "live", not "delivered".
  const label = channel === "web" && status === "sent" ? "Live" : OUTBOX_LABEL[status];
  return (
    <Chip tone={s.tone} icon={channel === "web" && status === "sent" ? Radio : s.icon}>
      {label}
    </Chip>
  );
}

/* -------------------------------------------------------- jobs and sources */

const JOB_STYLE: Record<ProcessingJobStatus, { tone: Tone; icon: LucideIcon }> = {
  succeeded: { tone: "emerald", icon: Check },
  failed: { tone: "red", icon: AlertTriangle },
  running: { tone: "indigo", icon: Loader2 },
  pending: { tone: "amber", icon: Hourglass },
  partial: { tone: "amber", icon: AlertTriangle },
  skipped: { tone: "slate", icon: MinusCircle },
};

export function JobStatusBadge({ status }: { status: ProcessingJobStatus }) {
  const s = JOB_STYLE[status];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {JOB_STATUS_LABEL[status]}
    </Chip>
  );
}

const CONNECTION_STYLE: Record<ConnectionStatus, { tone: Tone; icon: LucideIcon }> = {
  healthy: { tone: "emerald", icon: Check },
  degraded: { tone: "amber", icon: AlertTriangle },
  failing: { tone: "red", icon: AlertTriangle },
  disabled: { tone: "slate", icon: MinusCircle },
  untested: { tone: "slate", icon: CircleDashed },
};

export function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const s = CONNECTION_STYLE[status];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {CONNECTION_LABEL[status]}
    </Chip>
  );
}

const STAGE_STYLE: Record<PipelineStage["status"], { tone: Tone; icon: LucideIcon; label: string }> = {
  completed: { tone: "emerald", icon: Check, label: "Completed" },
  pending: { tone: "amber", icon: Hourglass, label: "Pending" },
  failed: { tone: "red", icon: AlertTriangle, label: "Failed" },
  skipped: { tone: "slate", icon: MinusCircle, label: "Skipped" },
};

export function StageStatus({ status }: { status: PipelineStage["status"] }) {
  const s = STAGE_STYLE[status];
  return (
    <Chip tone={s.tone} icon={s.icon}>
      {s.label}
    </Chip>
  );
}

export { STAGE_STYLE };
