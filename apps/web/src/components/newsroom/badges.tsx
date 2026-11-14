import { AlertTriangle, CheckCircle2, Clock, Eye, FileCheck2, Newspaper, XCircle } from "lucide-react";
import { Chip, type Tone } from "@/components/shared/status";
import {
  REVIEW_STATUS_LABEL,
  geographicLabel,
  newsCategoryLabel,
  type ArticleState,
  type ReviewStatus,
} from "@/lib/newsroom/taxonomy";
import type { NewsroomArticle } from "@/lib/newsroom/types";

const STATE: Record<ArticleState, { label: string; tone: Tone; icon: typeof Clock }> = {
  classified: { label: "Classified", tone: "emerald", icon: CheckCircle2 },
  pending: { label: "Waiting for classification", tone: "amber", icon: Clock },
  failed: { label: "Failed", tone: "red", icon: XCircle },
  skipped: { label: "Left out by an earlier road screen", tone: "slate", icon: Newspaper },
};

export function ArticleStateBadge({ state }: { state: ArticleState }) {
  const { label, tone, icon } = STATE[state];
  return (
    <Chip tone={tone} icon={icon}>
      {label}
    </Chip>
  );
}

const REVIEW_TONE: Record<ReviewStatus, Tone> = { new: "slate", reviewed: "indigo", used: "emerald", dismissed: "slate" };
const REVIEW_ICON = { new: Newspaper, reviewed: Eye, used: FileCheck2, dismissed: XCircle } as const;

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <Chip tone={REVIEW_TONE[status]} icon={REVIEW_ICON[status]}>
      {REVIEW_STATUS_LABEL[status]}
    </Chip>
  );
}

/** Primary category, with the AI marker: it is a machine reading, not an editor's decision. */
export function NewsCategoryBadge({ category }: { category: string | null }) {
  if (!category) return <span className="text-xs text-slate-500">Not classified</span>;
  return <Chip tone="indigo">{newsCategoryLabel(category)}</Chip>;
}

export function AttentionBadge({ article }: { article: Pick<NewsroomArticle, "needs_editorial_attention"> }) {
  if (!article.needs_editorial_attention) return null;
  return (
    <Chip tone="amber" icon={AlertTriangle}>
      Needs attention
    </Chip>
  );
}

export function BasisNote({ basis }: { basis: NewsroomArticle["classification_basis"] }) {
  if (!basis || basis === "full_text") return null;
  return (
    <span className="text-xs text-slate-600">
      {basis === "excerpt" ? "Read from the feed excerpt only" : "Read from the headline only"}
    </span>
  );
}

export { geographicLabel };
