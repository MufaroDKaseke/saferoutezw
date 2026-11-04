"use client";

import Link from "next/link";
import { useState } from "react";
import { FileSearch, RotateCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { BreadcrumbLabel } from "@/components/layout/breadcrumb-label";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfidenceBar } from "@/components/shared/meter";
import { PageHeader } from "@/components/shared/page-header";
import { PublisherLink, PrivacyNote, ContextNote } from "@/components/shared/notes";
import { ResourceView } from "@/components/shared/resource-view";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton } from "@/components/shared/states";
import { AiBadge, Chip, ExtractionBadge, RetrievalBadge, SyntheticBadge, WorkflowBadge } from "@/components/shared/status";
import { PipelineTimeline } from "@/components/shared/timeline";
import { useResource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { getNewsItem, retryNewsProcessing } from "@/lib/api/news";
import { formatDuration, formatFull, formatPercent, formatShort } from "@/lib/formatters/date";
import {
  INCIDENT_TYPE_LABEL,
  RETRIEVAL_METHOD_LABEL,
  SEVERITY_LABEL,
  SOURCE_KIND_LABEL,
} from "@/lib/formatters/labels";
import type { ExtractedEvent, ExtractionRun, SourceItemDetail } from "@/types";
import { KeywordChips } from "./keyword-chips";

export function ArticleDetail({ id }: { id: string }) {
  const article = useResource(`news:detail:${id}`, () => getNewsItem(id));
  return (
    <ResourceView resource={article} what="article" skeleton={<CardBodySkeleton lines={10} />}>
      {(a) => <ArticleView article={a} />}
    </ResourceView>
  );
}

function ArticleView({ article: a }: { article: SourceItemDetail }) {
  const [metaOpen, setMetaOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const latestRun = a.extractionRuns[a.extractionRuns.length - 1];

  const retry = async () => {
    setRetrying(true);
    try {
      const result = await retryNewsProcessing(a.id);
      toast.success(result.message);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="space-y-6">
      <BreadcrumbLabel path={`/news/${a.id}`} label={a.titleRedacted.length > 48 ? `${a.titleRedacted.slice(0, 46)}…` : a.titleRedacted} />
      <PageHeader
        meta={
          <>
            <WorkflowBadge state={a.workflowState} />
            {a.synthetic ? <SyntheticBadge /> : null}
            <span className="text-xs text-slate-600">
              Article {a.id} · {a.publisherName}
            </span>
          </>
        }
        title={a.titleRedacted}
        description="A source article and what the AI suggested from it. Nothing here confirms that an event happened."
        actions={
          <>
            {a.workflowState === "failed" ? (
              <Button variant="outline" size="lg" onClick={retry} disabled={retrying}>
                <RotateCw aria-hidden /> Retry processing
              </Button>
            ) : null}
            <Button variant="outline" size="lg" onClick={() => setMetaOpen(true)} disabled={a.extractionRuns.length === 0}>
              <FileSearch aria-hidden /> Extraction metadata
            </Button>
            {a.linkedIncidents.map((i) => (
              <Button key={i.id} asChild variant="default" size="lg">
                <Link href={`/incidents/${i.id}`}>View incident {i.referenceCode}</Link>
              </Button>
            ))}
          </>
        }
      />

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <SourcePanel article={a} />
        <AiPanel article={a} run={latestRun} />
      </div>

      <SectionCard title="Processing timeline" description="How this article moved through the pipeline, stage by stage.">
        <PipelineTimeline stages={a.pipeline} />
      </SectionCard>

      <MetadataDialog open={metaOpen} onOpenChange={setMetaOpen} runs={a.extractionRuns} />
    </div>
  );
}

/* ------------------------------------------------------------- left column */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="section-label">{label}</dt>
      <dd className="mt-1 text-sm break-words text-foreground">{children}</dd>
    </div>
  );
}

function SourcePanel({ article: a }: { article: SourceItemDetail }) {
  const c = a.content;
  return (
    <SectionCard
      title="Source article"
      description="What the publisher published, in the privacy-safe form the pipeline stored"
      action={
        a.canonicalUrl ? (
          <PublisherLink href={a.canonicalUrl} synthetic={a.synthetic} className="text-sm">
            View original article
          </PublisherLink>
        ) : null
      }
    >
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <Field label="Publisher">
          {a.publisherName} · {SOURCE_KIND_LABEL[a.sourceKind]}
        </Field>
        <Field label="Original address">
          <PublisherLink href={a.canonicalUrl} synthetic={a.synthetic}>
            {a.canonicalUrl ?? ""}
          </PublisherLink>
        </Field>
        <Field label="Published by the source">
          <span className="tnum">{formatFull(a.publishedAt)}</span>
        </Field>
        <Field label="Ingested by SafeRouteZW">
          <span className="tnum">{formatFull(a.receivedAt)}</span>
        </Field>
        <Field label="RSS title">{a.rssTitle}</Field>
        <Field label="RSS summary">{a.rssSummary ?? "None"}</Field>
      </dl>

      <div className="mt-5 space-y-3 border-t pt-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold">Readable article text</h3>
          <RetrievalBadge status={c.retrievalStatus} />
          {c.retrievalStatus === "retrieved" ? (
            <span className="tnum text-xs text-slate-600">
              {c.wordCount} words · {RETRIEVAL_METHOD_LABEL[c.method]} · {formatShort(c.retrievedAt)}
            </span>
          ) : null}
        </div>

        {c.retrievalStatus === "retrieved" ? (
          <>
            <PrivacyNote>
              {c.redactionCount > 0
                ? `${c.redactionCount} personal ${c.redactionCount === 1 ? "detail was" : "details were"} masked before storage and before AI processing. This is the privacy-safe version.`
                : "No personal details were found. This is the privacy-safe version."}
            </PrivacyNote>
            <div className="max-w-prose space-y-3 rounded-lg bg-slate-50 p-4 text-[15px] leading-relaxed text-slate-900">
              {c.paragraphs.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
            <p className="text-xs text-slate-600">
              {c.authors.length > 0 ? `By ${c.authors.join(", ")}. ` : ""}
              {c.imageCount} {c.imageCount === 1 ? "image" : "images"} not analysed.
            </p>
          </>
        ) : c.retrievalStatus === "failed" ? (
          <ContextNote>
            <p className="font-semibold">The full article could not be retrieved.</p>
            <p className="mt-0.5">{c.error}</p>
            <p className="mt-1">Only the RSS title and summary above are available.</p>
          </ContextNote>
        ) : c.retrievalStatus === "skipped" ? (
          <p className="text-sm text-slate-600">
            The full article was not fetched because the keyword screening filtered it out as not relevant to road safety.
          </p>
        ) : (
          <p className="text-sm text-slate-600">The full article has not been retrieved yet.</p>
        )}
      </div>

      <div className="mt-5 space-y-3 border-t pt-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold">Keyword screening</h3>
          {a.screening ? (
            <Chip tone="slate" className={a.screening.decision === "relevant" ? "bg-slate-900 text-white" : undefined}>
              {a.screening.decision === "relevant" ? "Relevant" : "Not relevant"}
            </Chip>
          ) : null}
        </div>
        {a.screening ? (
          <>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {a.screening.score !== null ? (
                <span className="flex items-center gap-2">
                  Relevance score <ConfidenceBar value={a.screening.score} />
                </span>
              ) : (
                <span>The keyword screen records a decision, not a score.</span>
              )}
              {a.screening.rulesetVersion ? (
                <span className="text-xs text-slate-600">Ruleset {a.screening.rulesetVersion}</span>
              ) : null}
            </div>
            <KeywordChips keywords={a.screening.matchedKeywords} />
            <p className="text-xs text-slate-600">Relevance only decides whether to read further. It is not verification.</p>
          </>
        ) : (
          <p className="text-sm text-slate-600">Not screened yet.</p>
        )}
      </div>
    </SectionCard>
  );
}

/* ------------------------------------------------------------ right column */

function AiPanel({ article: a, run }: { article: SourceItemDetail; run: ExtractionRun | undefined }) {
  return (
    <SectionCard
      title={
        <>
          <Sparkles className="size-4 text-indigo-600" aria-hidden /> AI intelligence
        </>
      }
      description="Suggestions extracted from the article text. Advisory only."
      action={<AiBadge>Suggestions, not facts</AiBadge>}
      className="ring-indigo-200"
    >
      <div className="space-y-5">
        <ContextNote>
          AI extraction is not editorial approval and not confirmation. An editor must review every incident candidate
          before anything becomes public.
        </ContextNote>

        {!run ? (
          <p className="text-sm text-slate-600">
            {a.workflowState === "filtered"
              ? "This article was filtered out by keyword screening, so it was never sent for extraction."
              : "No extraction has been run for this article yet."}
          </p>
        ) : (
          <>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Field label="Processing status">
                <ExtractionBadge status={run.status} />
              </Field>
              <Field label="Classification">
                {run.classification === "road_incident"
                  ? "Describes a road incident"
                  : run.classification === "not_road_incident"
                    ? "Not a road incident"
                    : run.classification === "uncertain"
                      ? "Uncertain"
                      : "Not available"}
              </Field>
              <Field label="Events detected">{run.status === "succeeded" ? run.events.length : "–"}</Field>
              <Field label="Model confidence">
                {run.confidence != null ? (
                  <span className="flex items-center gap-2">
                    <ConfidenceBar value={run.confidence} />
                    <span className="text-xs text-slate-600">self-reported</span>
                  </span>
                ) : (
                  "–"
                )}
              </Field>
              <Field label="Model">
                {run.modelName}
                {run.modelVersion ? ` · ${run.modelVersion}` : ""}
              </Field>
              <Field label="Extracted at">
                <span className="tnum">{formatFull(run.createdAt)}</span>
              </Field>
            </dl>

            {run.status === "failed" ? (
              <ContextNote>
                <p className="font-semibold">Extraction failed.</p>
                <p className="mt-0.5">{run.errorMessage}</p>
                {run.schemaValidation && run.schemaValidation.errors.length > 0 ? (
                  <ul className="mt-1.5 list-disc pl-5 text-xs">
                    {run.schemaValidation.errors.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                ) : null}
              </ContextNote>
            ) : null}

            {run.status === "pending" ? <p className="text-sm text-slate-600">Queued. The model has not responded yet.</p> : null}

            {run.status === "succeeded" && run.events.length === 0 ? (
              <p className="text-sm text-slate-600">No events were extracted, so no incident candidate was created.</p>
            ) : null}

            {run.events.map((event, index) => (
              <EventCard key={event.id} event={event} index={index} total={run.events.length} />
            ))}
          </>
        )}
      </div>
    </SectionCard>
  );
}

function EventCard({ event: e, index, total }: { event: ExtractedEvent; index: number; total: number }) {
  return (
    <article className="space-y-4 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4" aria-label={`Extracted event ${index + 1} of ${total}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold">
          {total > 1 ? `Event ${index + 1} of ${total}: ` : ""}
          {INCIDENT_TYPE_LABEL[e.incidentType]}
        </h3>
        {e.linkedIncidentId ? (
          <Link href={`/incidents/${e.linkedIncidentId}`} className="text-sm font-semibold text-emerald-800 hover:underline">
            Linked incident candidate
          </Link>
        ) : (
          <Chip tone="slate">No incident candidate created</Chip>
        )}
      </header>

      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        <Field label="Location">{e.locationText ?? "Not stated"}</Field>
        <Field label="Road">{e.roadName ?? "Not stated"}</Field>
        <Field label="Kilometre peg">{e.kmPeg ?? "Not stated"}</Field>
        <Field label="Reported time">{e.occurredAtText ?? "Not stated"}</Field>
        <Field label="Vehicles">{e.vehicles.length ? e.vehicles.join(", ") : "None stated"}</Field>
        <Field label="Traffic impact">{e.trafficImpact ?? "None stated"}</Field>
        {e.injuries ? <Field label="Injuries (as reported)">{e.injuries}</Field> : null}
        {e.fatalities ? <Field label="Fatalities (as reported)">{e.fatalities}</Field> : null}
        <Field label="Suggested severity">
          {SEVERITY_LABEL[e.suggestedSeverity]} <span className="text-xs text-slate-600">(AI suggestion)</span>
        </Field>
        <Field label="Event confidence">
          <ConfidenceBar value={e.confidence} />
        </Field>
      </dl>

      {e.evidenceSnippets.length > 0 ? (
        <div>
          <h4 className="section-label mb-1.5">Evidence from the article</h4>
          <ul className="space-y-2">
            {e.evidenceSnippets.map((s) => (
              <li key={`${s.field}-${s.text}`} className="rounded-md border-l-4 border-indigo-300 bg-white px-3 py-2 text-sm">
                <span className="block text-xs font-medium text-slate-600">{s.field}</span>
                <q className="text-slate-900">{s.text}</q>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {e.missingInformation.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <h4 className="mb-1.5 text-sm font-bold text-amber-950">Missing information</h4>
          <ul className="space-y-1.5">
            {e.missingInformation.map((m) => (
              <li key={m} className="flex gap-2 text-sm text-amber-950">
                <span className="mt-0.5 h-fit shrink-0 rounded border border-amber-400 px-1 text-[10px] font-bold text-amber-800">GAP</span>
                {m}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

/* ---------------------------------------------------------------- metadata */

function MetadataDialog({
  open,
  onOpenChange,
  runs,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runs: ExtractionRun[];
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Extraction metadata</DialogTitle>
          <DialogDescription>
            Every attempt is kept. Confidence is the model’s own score for how well it extracted fields; it does not
            establish that an incident occurred.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {runs.map((r, i) => (
            <section key={r.id} className="rounded-lg border p-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold">
                Attempt {i + 1} <ExtractionBadge status={r.status} />
              </h3>
              <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-slate-600">Run reference</dt>
                  <dd className="font-mono text-xs">{r.id}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600">Model</dt>
                  <dd>
                    {r.modelName} {r.modelVersion ?? ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600">Created</dt>
                  <dd className="tnum">{formatFull(r.createdAt)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600">Duration</dt>
                  <dd className="tnum">{formatDuration(r.durationMs)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600">Model confidence</dt>
                  <dd className="tnum">{formatPercent(r.confidence)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-600">Schema validation</dt>
                  <dd>{r.schemaValidation ? (r.schemaValidation.passed ? "Passed" : "Failed") : "Not run"}</dd>
                </div>
              </dl>
              {r.errorMessage ? <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-900">{r.errorMessage}</p> : null}
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

