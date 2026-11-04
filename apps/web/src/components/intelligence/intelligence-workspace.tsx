"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ContextNote, SimulationNote } from "@/components/shared/notes";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, QueryError } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { isMockMode } from "@/lib/api/config";
import { errorMessage } from "@/lib/api/errors";
import {
  getIntelligence,
  publishIntelligence,
  reviewIntelligence,
  saveIntelligenceVersion,
  withdrawIntelligenceOutput,
  type IntelligenceDetail,
} from "@/lib/api/intelligence";
import { OUTPUT_LABEL, categoryLabel, formatFigure, formatPeriod, geographicScopeLabel, isActionableKind, subtypeLabel } from "@/lib/domain/intelligence";
import { formatShort } from "@/lib/formatters/date";
import {
  CATEGORY_LABELS,
  GEOGRAPHIC_SCOPES,
  PRIMARY_CATEGORIES,
  SUBTYPES,
  type GeographicScope,
  type PrimaryCategory,
  type PublicationOutputType,
} from "@/lib/taxonomy.generated";
import { CategoryBadge, RecordKindBadge, RecordStatusBadge } from "./badges";

const SELECT =
  "h-10 w-full rounded-lg border border-input bg-card px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50";

type FigureChoice = "unverified" | "verified" | "rejected";

function humanize(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function renderValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((v) => (typeof v === "object" && v ? Object.values(v as object).filter((x) => x !== null).join(" ") : String(v))).join("; ");
  }
  return String(value);
}

/** Extracted category-specific facts. Empty values are omitted, never shown as zero. */
function DetailList({ details }: { details: Record<string, unknown> }) {
  const rows = Object.entries(details).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0));
  if (rows.length === 0) return <p className="text-sm text-slate-600">The model extracted no category-specific facts.</p>;
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs font-semibold text-slate-600">{humanize(key)}</dt>
          <dd>{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function IntelligenceWorkspace({ id }: { id: string }) {
  const record = useResource(`intelligence:${id}`, () => getIntelligence(id));
  if (record.error) return <QueryError error={record.error} onRetry={record.refetch} what="intelligence record" />;
  if (!record.data) return <CardBodySkeleton lines={10} />;
  return <Workspace key={`${record.data.id}:${record.data.versions.length}:${record.data.status}`} data={record.data} reload={record.refetch} />;
}

function Workspace({ data, reload }: { data: IntelligenceDetail; reload: () => void }) {
  const { user } = useSession();
  const canEdit = user?.role === "admin" || user?.role === "editor";
  const latest = data.versions[0] ?? null;
  const editable = canEdit && ["candidate", "under_review", "approved"].includes(data.status);

  const [headline, setHeadline] = useState(latest?.headline ?? data.headline);
  const [summary, setSummary] = useState(latest?.summary ?? data.summary);
  const [category, setCategory] = useState<PrimaryCategory>((latest?.primary_category ?? data.primary_category) as PrimaryCategory);
  const [subtype, setSubtype] = useState<string>(latest ? (latest.primary_subtype ?? "") : (data.primary_subtype ?? ""));
  const [scope, setScope] = useState<GeographicScope>((latest?.geographic_scope ?? data.geographic_scope) as GeographicScope);
  const [eventDate, setEventDate] = useState(latest?.event_date ?? data.event_date ?? "");
  const [attribution, setAttribution] = useState(latest?.source_attribution ?? data.source_attribution ?? "");
  const [changeNote, setChangeNote] = useState("");
  const [figures, setFigures] = useState<Record<string, FigureChoice>>(
    Object.fromEntries(data.observations.map((o) => [o.id, o.verification_status as FigureChoice])),
  );
  const [notes, setNotes] = useState("");
  const [output, setOutput] = useState<PublicationOutputType>((data.allowed_outputs[0] ?? "transport_news") as PublicationOutputType);
  const [busy, setBusy] = useState(false);

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      toast.success(label);
      reload();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const save = () =>
    run("New version saved", () =>
      saveIntelligenceVersion(data.id, {
        headline,
        summary,
        primary_category: category,
        primary_subtype: subtype || null,
        geographic_scope: scope,
        event_date: eventDate || null,
        source_attribution: attribution || null,
        change_note: changeNote || null,
        base_version: latest?.version_number ?? null,
        figure_decisions: data.observations
          .filter((o) => figures[o.id] !== o.verification_status)
          .map((o) => ({ observation_id: o.id, status: figures[o.id] })),
      }),
    );

  const decide = (decision: "approved" | "rejected" | "needs_changes") =>
    run(`Decision recorded: ${decision.replace("_", " ")}`, () =>
      reviewIntelligence(data.id, { decision, version_id: latest?.id ?? null, notes: notes || null }),
    );

  const standing = data.reviews[0]?.decision === "approved" && data.reviews[0]?.version_number === latest?.version_number;
  const reviewable = canEdit && ["candidate", "under_review"].includes(data.status);
  const needsNotes = !notes.trim();
  const actionable = isActionableKind(data.record_kind);

  return (
    <div className="space-y-6">
      <PageHeader
        title={data.headline}
        meta={
          <>
            <CategoryBadge category={data.primary_category} subtype={data.primary_subtype} />
            <RecordKindBadge kind={data.record_kind} />
            <RecordStatusBadge status={data.status} />
          </>
        }
        description={data.summary}
        actions={
          data.incident_id ? (
            <Button asChild variant="outline">
              <Link href={`/incidents/${data.incident_id}`}>Open linked road event</Link>
            </Button>
          ) : undefined
        }
      />

      {isMockMode() ? <SimulationNote>Demo data. Saving, deciding and publishing need the live API.</SimulationNote> : null}
      <ContextNote>
        {actionable
          ? "This is a specific road event. It is also an incident candidate, and a public hazard alert needs the incident's own approval and publication."
          : "This is background intelligence, not a road event. Publishing it never creates a road hazard alert."}{" "}
        Everything below was read by an AI model and is unverified until you approve a version.
      </ContextNote>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <SectionCard title="Extracted facts" description={`${categoryLabel(data.primary_category)} · ${geographicScopeLabel(data.geographic_scope)} · AI confidence ${Math.round(data.classification_confidence * 100)}%`}>
            <DetailList details={data.details} />
            <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div><dt className="text-xs font-semibold text-slate-600">Place</dt><dd>{[data.road_name, data.district_or_town, data.province, data.country].filter(Boolean).join(", ") || "Not stated"}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-600">Date</dt><dd>{data.event_date ?? "Not stated"}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-600">Status of the event</dt><dd>{humanize(data.temporal_status)}</dd></div>
              <div><dt className="text-xs font-semibold text-slate-600">Attributed to</dt><dd>{data.source_attribution ?? "Not stated"}</dd></div>
            </dl>
            {Array.isArray((data.quality as { flags?: string[] }).flags) && (data.quality as { flags: string[] }).flags.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {(data.quality as { flags: string[] }).flags.map((f) => <Chip key={f} tone="amber">{humanize(f)}</Chip>)}
              </div>
            ) : null}
            {Array.isArray((data.quality as { missing_information?: string[] }).missing_information) && (data.quality as { missing_information: string[] }).missing_information.length > 0 ? (
              <p className="mt-3 text-xs text-slate-600">Missing: {(data.quality as { missing_information: string[] }).missing_information.join("; ")}</p>
            ) : null}
          </SectionCard>

          <SectionCard title="Source" description="Check every fact against the original before approving.">
            <ul className="space-y-2 text-sm">
              {data.citations.map((c) => (
                <li key={`${c.source_name}${c.url}`}>
                  <span className="font-semibold">{c.source_name}</span> · {formatShort(c.published_at)}
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer noopener" className="ml-2 inline-flex items-center gap-1 text-emerald-800 hover:underline">
                      Open original <ExternalLink className="size-3" aria-hidden />
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
            {Array.isArray((data.quality as { evidence?: string[] }).evidence) ? (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {((data.quality as { evidence: string[] }).evidence).map((q) => <li key={q}>&ldquo;{q}&rdquo;</li>)}
              </ul>
            ) : null}
          </SectionCard>

          {data.observations.length > 0 ? (
            <SectionCard title="Reported figures" description="Verify or reject each figure against the source. Periods and sources are kept apart; figures are never added together.">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Statistical figures extracted from the source</caption>
                  <thead className="text-left text-xs text-slate-600">
                    <tr><th className="py-1.5 pr-3">Figure</th><th className="pr-3">Period</th><th className="pr-3">Coverage and source</th><th>Check</th></tr>
                  </thead>
                  <tbody>
                    {data.observations.map((o) => (
                      <tr key={o.id} className="border-t align-top">
                        <td className="py-2 pr-3"><strong className="tnum">{formatFigure(o.value, o.unit)}</strong><br />{o.metric}{o.is_preliminary ? <Chip tone="amber" className="ml-1">Preliminary</Chip> : null}</td>
                        <td className="pr-3">{formatPeriod(o.period_start, o.period_end)}</td>
                        <td className="pr-3 text-xs">{o.geographic_coverage ?? "Coverage not stated"}<br />{o.source_reference ?? "Source not stated"}{o.methodology ? <><br />{o.methodology}</> : null}</td>
                        <td>
                          <select aria-label={`Check ${o.metric}`} className={SELECT} disabled={!editable} value={figures[o.id]} onChange={(e) => setFigures((f) => ({ ...f, [o.id]: e.target.value as FigureChoice }))}>
                            <option value="unverified">Not checked</option>
                            <option value="verified">Verified</option>
                            <option value="rejected">Reject</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          ) : null}

          <SectionCard title="Version history" description="Saved versions are never changed. An approval covers exactly one version.">
            {data.versions.length === 0 ? <p className="text-sm text-slate-600">No editorial version yet. Save one to start review.</p> : (
              <ol className="space-y-3 text-sm">
                {data.versions.map((v) => (
                  <li key={v.id} className="rounded-lg border p-3">
                    <p className="font-semibold">Version {v.version_number}{v.is_latest ? " (latest)" : ""} · {v.created_by_name} · {formatShort(v.created_at)}</p>
                    <p>{v.headline}</p>
                    <p className="text-xs text-slate-600">{categoryLabel(v.primary_category)} / {subtypeLabel(v.primary_subtype)} / {geographicScopeLabel(v.geographic_scope)}{v.change_note ? ` · ${v.change_note}` : ""}</p>
                  </li>
                ))}
              </ol>
            )}
            {data.reviews.length > 0 ? (
              <ul className="mt-4 space-y-1 text-xs text-slate-600">
                {data.reviews.map((r) => <li key={r.id}>{formatShort(r.reviewed_at)} · {r.reviewer_name}: {r.decision.replace("_", " ")} on version {r.version_number ?? "none"}{r.notes ? ` · ${r.notes}` : ""}</li>)}
              </ul>
            ) : null}
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Edit and save a version" description={canEdit ? "Correct anything the AI got wrong. Saving creates a new version and returns the record to review." : "Only editors and admins can edit."}>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
              <div><Label htmlFor="iw-headline">Headline</Label><Input id="iw-headline" value={headline} onChange={(e) => setHeadline(e.target.value)} disabled={!editable} maxLength={200} /></div>
              <div><Label htmlFor="iw-summary">Neutral summary</Label><Textarea id="iw-summary" value={summary} onChange={(e) => setSummary(e.target.value)} disabled={!editable} maxLength={2000} rows={5} /></div>
              <div>
                <Label htmlFor="iw-category">Primary category</Label>
                <select id="iw-category" className={SELECT} disabled={!editable} value={category} onChange={(e) => { setCategory(e.target.value as PrimaryCategory); setSubtype(""); }}>
                  {PRIMARY_CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
                </select>
              </div>
              <div>
                <Label htmlFor="iw-subtype">Subtype</Label>
                <select id="iw-subtype" className={SELECT} disabled={!editable} value={subtype} onChange={(e) => setSubtype(e.target.value)}>
                  <option value="">No subtype</option>
                  {SUBTYPES[category].map((s) => <option key={s} value={s}>{subtypeLabel(s)}</option>)}
                </select>
              </div>
              <div>
                <Label htmlFor="iw-scope">Geographic scope</Label>
                <select id="iw-scope" className={SELECT} disabled={!editable} value={scope} onChange={(e) => setScope(e.target.value as GeographicScope)}>
                  {GEOGRAPHIC_SCOPES.map((s) => <option key={s} value={s}>{geographicScopeLabel(s)}</option>)}
                </select>
              </div>
              <div><Label htmlFor="iw-date">Event or announcement date</Label><Input id="iw-date" type="date" value={eventDate} onChange={(e) => setEventDate(e.target.value)} disabled={!editable} /></div>
              <div><Label htmlFor="iw-attr">Source attribution</Label><Input id="iw-attr" value={attribution} onChange={(e) => setAttribution(e.target.value)} disabled={!editable} maxLength={300} /></div>
              <div><Label htmlFor="iw-note">What changed</Label><Input id="iw-note" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} disabled={!editable} /></div>
              <Button type="submit" disabled={!editable || busy || !headline.trim() || !summary.trim()}>Save new version</Button>
            </form>
          </SectionCard>

          <SectionCard title="Decision" description="Applies to the latest saved version only.">
            <div className="space-y-3">
              <Label htmlFor="iw-notes">Notes (required to reject or request changes)</Label>
              <Textarea id="iw-notes" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={!reviewable} rows={3} maxLength={2000} />
              {!latest ? <p className="text-xs text-slate-600">Save a version before approving.</p> : null}
              <div className="flex flex-wrap gap-2">
                <Button disabled={!reviewable || busy || !latest} onClick={() => decide("approved")}>Approve version {latest?.version_number ?? ""}</Button>
                <Button variant="outline" disabled={!reviewable || busy || needsNotes} onClick={() => decide("needs_changes")}>Request changes</Button>
                <Button variant="outline" disabled={!reviewable || busy || needsNotes} onClick={() => decide("rejected")}>Reject</Button>
              </div>
              {!reviewable && canEdit ? <p className="text-xs text-slate-600">A {data.status.replace("_", " ")} record cannot be decided on.</p> : null}
            </div>
          </SectionCard>

          <SectionCard title="Publication" description="Separate from approval. Choose what this becomes on the public site.">
            {data.outputs.length > 0 ? (
              <ul className="mb-3 space-y-2 text-sm">
                {data.outputs.map((o) => (
                  <li key={o.id} className="flex items-center justify-between gap-2">
                    <span>{OUTPUT_LABEL[o.output_type as PublicationOutputType]} · v{o.version_number} · {o.status}</span>
                    {o.status === "published" && canEdit ? <Button size="sm" variant="outline" disabled={busy} onClick={() => run("Withdrawn", () => withdrawIntelligenceOutput(o.id))}>Withdraw</Button> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="space-y-3">
              <Label htmlFor="iw-output">Publish as</Label>
              <select id="iw-output" className={SELECT} value={output} onChange={(e) => setOutput(e.target.value as PublicationOutputType)} disabled={!canEdit}>
                {data.allowed_outputs.map((o) => <option key={o} value={o}>{OUTPUT_LABEL[o as PublicationOutputType]}</option>)}
              </select>
              <Button disabled={!canEdit || busy || !standing || !["approved", "published"].includes(data.status)} onClick={() => run("Published", () => publishIntelligence(data.id, output))}>
                Publish
              </Button>
              {!standing ? <p className="text-xs text-slate-600">Publishing needs a standing approval on the latest version.</p> : null}
              <p className="text-xs text-slate-600">This is not a road hazard alert. Hazard alerts come only from approved and published incidents.</p>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
