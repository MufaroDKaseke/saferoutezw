"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ExternalLink, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { NotFoundState, QueryError, CardBodySkeleton } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useResource } from "@/hooks/use-resource";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { getNewsroomArticle, retryNewsroomArticle, setArticleReview } from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import { REVIEW_STATUSES, REVIEW_STATUS_LABEL, geographicLabel, type ReviewStatus } from "@/lib/newsroom/taxonomy";
import { ArticleStateBadge, AttentionBadge, BasisNote, NewsCategoryBadge, ReviewStatusBadge } from "./badges";

function ChipList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="section-label mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <Chip key={item}>{item}</Chip>
        ))}
      </div>
    </div>
  );
}

export function NewsroomArticleDetail({ id }: { id: string }) {
  const article = useResource(`newsroom:article:${id}`, () => getNewsroomArticle(id));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  if (article.error) {
    if (article.error instanceof ApiError && article.error.status === 404) {
      return <NotFoundState what="article" action={<Link href="/news">Back to the News Monitor</Link>} />;
    }
    return <QueryError error={article.error} onRetry={article.refetch} what="article" />;
  }
  const a = article.data;
  if (!a) return <CardBodySkeleton lines={8} />;

  const act = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await work();
      toast.success(done);
      article.refetch();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link href="/news" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> News Monitor
      </Link>

      <PageHeader
        meta={
          <>
            <NewsCategoryBadge category={a.category} />
            {a.secondary_category ? <NewsCategoryBadge category={a.secondary_category} /> : null}
            <ArticleStateBadge state={a.state} />
            <ReviewStatusBadge status={a.review.status} />
            <AttentionBadge article={a} />
          </>
        }
        title={a.headline}
        description={
          <>
            {a.publisher} · published {formatFull(a.published_at, "date not given")} · collected {formatFull(a.collected_at)}
          </>
        }
        actions={
          a.source_url ? (
            <Button asChild variant="outline">
              <a href={a.source_url} target="_blank" rel="noopener noreferrer">
                Original article <ExternalLink aria-hidden />
              </a>
            </Button>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <SectionCard title="Article text" description="Personal details are redacted before storage. This is what the AI read.">
            {a.article_text || a.excerpt ? (
              <div className="max-h-[32rem] overflow-y-auto text-sm leading-relaxed whitespace-pre-line text-slate-800">
                {a.article_text ?? a.excerpt}
              </div>
            ) : (
              <p className="text-sm text-slate-600">No article text was stored. Open the original article.</p>
            )}
            {a.fetch_error ? <p className="mt-3 text-xs text-slate-600">Retrieval note: {a.fetch_error}</p> : null}
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard
            title="AI summary"
            description="A machine reading of the article. It can be wrong and does not check facts."
          >
            {a.summary ? (
              <div className="space-y-4">
                <p className="text-sm leading-relaxed">{a.summary}</p>
                <ChipList label="Topics" items={a.topics} />
                <ChipList label="Organisations" items={a.organisations} />
                <ChipList label="Places" items={a.places} />
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="section-label">Geographic relevance</dt>
                    <dd>{geographicLabel(a.geographic_relevance)}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Classification clarity</dt>
                    <dd className="tnum">
                      {a.classification_confidence === null ? "—" : `${Math.round(a.classification_confidence * 100)}%`}
                    </dd>
                  </div>
                </dl>
                <p className="text-xs text-slate-600">
                  Clarity shows how clearly the text supports the category. It is not the chance that the article is true.
                </p>
                {a.needs_editorial_attention ? (
                  <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                    <strong>Needs attention:</strong> {a.attention_reason ?? "flagged by the classifier"}
                  </p>
                ) : null}
                <p className="text-xs text-slate-600">
                  <BasisNote basis={a.classification_basis} />
                  {a.model ? ` ${a.model} · ${a.prompt_version}` : ""}
                  {a.reused_from ? " · copied from an identical article" : ""}
                </p>
              </div>
            ) : a.state === "failed" ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-700">This article could not be classified. {a.last_error ?? a.fetch_error}</p>
                <Button disabled={busy} onClick={() => act(() => retryNewsroomArticle(id), "Queued again")}>
                  <RotateCcw aria-hidden /> Try again
                </Button>
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                {a.state === "pending" ? "Waiting to be classified." : "This article has no classification."}
              </p>
            )}
          </SectionCard>

          <SectionCard title="Newsroom review" description="Mark what the newsroom has done with this article. It never publishes anything.">
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2" role="group" aria-label="Review status">
                {REVIEW_STATUSES.map((status: ReviewStatus) => (
                  <Button
                    key={status}
                    variant={a.review.status === status ? "default" : "outline"}
                    disabled={busy}
                    aria-pressed={a.review.status === status}
                    onClick={() => act(() => setArticleReview(id, status, note), `Marked ${REVIEW_STATUS_LABEL[status].toLowerCase()}`)}
                  >
                    {REVIEW_STATUS_LABEL[status]}
                  </Button>
                ))}
              </div>
              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional note (for example: used in the 6pm bulletin)"
                maxLength={500}
                aria-label="Review note"
              />
              {a.review.at ? (
                <p className="text-xs text-slate-600">
                  Last set by {a.review.by ?? "someone"} on {formatFull(a.review.at)}
                  {a.review.note ? ` — “${a.review.note}”` : ""}
                </p>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
