"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import { ArrowRight, Check, Lock, PencilLine, Sparkles, User, X } from "lucide-react";
import { toast } from "sonner";
import { BreadcrumbLabel } from "@/components/layout/breadcrumb-label";
import { AssessmentCards, EvidenceList, MissingInformation } from "@/components/incidents/assessments";
import { DEFAULT_LAYERS } from "@/components/maps/map-logic";
import { SafetyMap } from "@/components/maps/safety-map-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote, PrivacyNote, SimulationNote } from "@/components/shared/notes";
import { ResourceView } from "@/components/shared/resource-view";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton } from "@/components/shared/states";
import { AiBadge, Chip, PriorityBadge, ReviewStateBadge, SyntheticBadge, type Tone } from "@/components/shared/status";
import { AuditTimeline } from "@/components/shared/timeline";
import { useDemoSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { listAlerts } from "@/lib/api/alerts";
import { getDataMode } from "@/lib/api/config";
import { ValidationError, errorMessage } from "@/lib/api/errors";
import { approveIncident, getReviewWorkspace, rejectIncident, requestChanges, saveDraft } from "@/lib/api/reviews";
import {
  REDACTION_PATTERN,
  LOCATION_CONFIRMATION_LABEL,
  checkBulletin,
  type LocationConfirmation,
} from "@/lib/domain/bulletin-checks";
import { INCIDENT_TYPE_OPTIONS } from "@/lib/domain/constants";
import { confidenceBand } from "@/lib/domain/derive";
import { formatFull, formatPercent, formatShort } from "@/lib/formatters/date";
import { INCIDENT_TYPE_LABEL, PRIORITY_LABEL, SEVERITY_LABEL } from "@/lib/formatters/labels";
import type { ExtractedEvent, IncidentType, ReviewWorkspace } from "@/types";
import { ApproveDialog, RejectDialog, RequestChangesDialog } from "./decision-dialogs";
import { LocationPanel } from "./location-panel";

export function ReviewWorkspaceView({ id }: { id: string }) {
  const workspace = useResource(`review:${id}`, () => getReviewWorkspace(id));
  return (
    <ResourceView resource={workspace} what="report" skeleton={<CardBodySkeleton lines={12} />}>
      {(ws) => <Body ws={ws} onChanged={workspace.refetch} />}
    </ResourceView>
  );
}

function Body({ ws, onChanged }: { ws: ReviewWorkspace; onChanged: () => void }) {
  const i = ws.incident;
  const final = ws.state === "approved" || ws.state === "rejected";
  const mock = getDataMode() === "mock";

  return (
    <div className="space-y-6">
      <BreadcrumbLabel path={`/reviews/${i.id}`} label={i.referenceCode} />
      <PageHeader
        meta={
          <>
            <span className="font-mono text-sm font-semibold">{i.referenceCode}</span>
            <ReviewStateBadge state={ws.state} />
            <Chip tone="amber">Suggested priority: {PRIORITY_LABEL[i.reviewPriority]}</Chip>
            {i.synthetic ? <SyntheticBadge /> : null}
          </>
        }
        title={i.title}
        description="The AI has extracted and organised this report. You decide what, if anything, becomes public."
        actions={<Ribbon />}
      />

      {mock ? (
        <SimulationNote>
          <strong>Demo mode.</strong> Decisions here change the demo only. No alert can be sent from this screen, and
          nothing is saved to the database.
        </SimulationNote>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <EvidencePanel ws={ws} />
        <div className="space-y-6">
          <AiPanel ws={ws} />
          {final ? <DecisionRecord ws={ws} /> : <EditorPanel key={`${i.id}:${ws.bulletins[0]?.id ?? "none"}`} ws={ws} onChanged={onChanged} />}
          <SectionCard title="Review history" description="Append-only. Entries are never edited." action={<Chip tone="slate" icon={Lock}>Append-only log</Chip>}>
            <AuditTimeline events={ws.history} />
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function Ribbon() {
  return (
    <div className="inline-flex items-stretch overflow-hidden rounded-lg text-sm font-semibold" aria-label="AI suggests, the editor decides">
      <span className="flex items-center gap-1.5 bg-indigo-100 px-3.5 py-2.5 text-indigo-900">
        <Sparkles className="size-4" aria-hidden /> AI suggests
      </span>
      <span className="flex items-center bg-slate-200 px-1.5 text-slate-600" aria-hidden>
        <ArrowRight className="size-3.5" />
      </span>
      <span className="flex items-center gap-1.5 bg-slate-900 px-3.5 py-2.5 text-white">
        <User className="size-4" aria-hidden /> Editor decides
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- evidence */

/** Shows the pipeline's redaction markers as solid bars, so it is obvious what was withheld. */
function RedactedText({ text }: { text: string }) {
  const parts = text.split(REDACTION_PATTERN);
  const marks = text.match(REDACTION_PATTERN) ?? [];
  return (
    <>
      {parts.map((part, idx) => (
        <Fragment key={idx}>
          {part}
          {idx < marks.length ? (
            <span className="mx-0.5 inline-block h-[0.9em] w-20 rounded-sm bg-slate-900 align-middle" role="img" aria-label="redacted">
              <span className="sr-only">redacted</span>
            </span>
          ) : null}
        </Fragment>
      ))}
    </>
  );
}

function band(conf: number): { tone: Tone; label: string } {
  const b = confidenceBand(conf);
  if (b === "high") return { tone: "emerald", label: "High confidence" };
  if (b === "medium") return { tone: "amber", label: "Medium confidence" };
  return { tone: "slate", label: "Low confidence" };
}

function ExtractedRow({ label, value, chip }: { label: string; value: React.ReactNode; chip: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] items-start gap-x-3 gap-y-1.5 border-b border-slate-100 py-3 last:border-0 sm:grid-cols-[8.5rem_1fr_auto]">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
      <dd className="col-start-2 sm:col-start-3">{chip}</dd>
    </div>
  );
}

function whyConfidence(e: ExtractedEvent, pct: string): string {
  const clear: string[] = ["incident type"];
  if (e.vehicles.length) clear.push("vehicle types");
  if (e.trafficImpact) clear.push("traffic effect");
  const vague: string[] = [];
  if (!e.kmPeg) vague.push(e.locationText ? "the exact location is given only by road and landmark" : "no location is given");
  if (!e.occurredAt) vague.push("the time is not stated");
  return `Why ${pct}? ${clear.join(" and ").replace(/^./, (c) => c.toUpperCase())} ${clear.length > 1 ? "are" : "is"} stated clearly${vague.length ? `, but ${vague.join(" and ")}` : ""}.`;
}

function EvidencePanel({ ws }: { ws: ReviewWorkspace }) {
  const i = ws.incident;
  const e = ws.primaryEvent;
  return (
    <div className="space-y-6">
      <SectionCard title="Incident evidence" action={<span className="section-label">Original · unedited</span>}>
        <div className="space-y-4">
          {ws.evidenceText.map((block) => (
            <figure key={block.sourceItemId} className="rounded-xl border bg-slate-50 p-4">
              <figcaption className="mb-2 text-xs text-slate-600">
                <Link href={`/news/${block.sourceItemId}`} className="font-semibold text-foreground hover:underline">
                  {block.articleTitle}
                </Link>{" "}
                · {block.publisherName}
              </figcaption>
              <div className="max-w-prose space-y-2.5 text-[15px] leading-relaxed">
                {block.paragraphs.map((p, idx) => (
                  <p key={idx}>
                    <RedactedText text={p} />
                  </p>
                ))}
              </div>
            </figure>
          ))}
          <PrivacyNote>Sender names and phone numbers are protected and hidden from the public and from the AI summary.</PrivacyNote>
        </div>
        <dl className="mt-5 grid gap-x-6 gap-y-4 border-t pt-5 sm:grid-cols-2">
          <div>
            <dt className="section-label">Sources</dt>
            <dd className="mt-1 text-sm font-medium">
              {i.sourceCount} {i.sourceCount === 1 ? "article" : "articles"}
            </dd>
          </div>
          <div>
            <dt className="section-label">Received</dt>
            <dd className="tnum mt-1 text-sm font-medium">{formatFull(i.createdAt)}</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard title="Source articles" description="Where each piece of evidence comes from">
        <EvidenceList evidence={i.evidence} />
      </SectionCard>

      {e ? (
        <SectionCard
          title="AI-extracted details"
          action={<AiBadge>Suggestions, not facts</AiBadge>}
        >
          <dl>
            <ExtractedRow
              label="Incident type"
              value={INCIDENT_TYPE_LABEL[e.incidentType]}
              chip={<Chip tone={band(e.confidence).tone}>{band(e.confidence).label}</Chip>}
            />
            <ExtractedRow
              label="Location"
              value={e.locationText ?? "Not stated"}
              chip={e.locationText ? <Chip tone={e.kmPeg ? "emerald" : "amber"}>{e.kmPeg ? "High confidence" : "Medium confidence"}</Chip> : <Chip tone="slate">Unknown</Chip>}
            />
            <ExtractedRow
              label="Incident time"
              value={e.occurredAtText ?? "Not stated"}
              chip={e.occurredAt ? <Chip tone="emerald">Stated</Chip> : <Chip tone="slate">Unknown</Chip>}
            />
            <ExtractedRow
              label="Vehicles"
              value={e.vehicles.length ? e.vehicles.join(" and ") : "None stated"}
              chip={e.vehicles.length ? <Chip tone={band(e.confidence).tone}>{band(e.confidence).label}</Chip> : <Chip tone="slate">Unknown</Chip>}
            />
            <ExtractedRow
              label="Injuries"
              value={e.injuries ?? "None stated"}
              chip={e.injuries ? <Chip tone="red">Unverified</Chip> : <Chip tone="slate">Not stated</Chip>}
            />
            <ExtractedRow label="Suggested severity" value={SEVERITY_LABEL[e.suggestedSeverity]} chip={<AiBadge />} />
          </dl>
          <p className="mt-3 border-t pt-3 text-xs leading-relaxed text-slate-600">
            <strong className="text-slate-900">{whyConfidence(e, formatPercent(e.confidence)).split("?")[0]}?</strong>
            {whyConfidence(e, formatPercent(e.confidence)).split("?").slice(1).join("?")}
          </p>
        </SectionCard>
      ) : null}

      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="mb-3 text-base font-bold text-amber-950">Missing information and uncertainty</h2>
        <MissingInformation items={i.missingInformation} />
      </div>
    </div>
  );
}

/* --------------------------------------------------------- AI intelligence */

function AiPanel({ ws }: { ws: ReviewWorkspace }) {
  const i = ws.incident;
  const nearest = i.blackspotMatches[0];
  return (
    <SectionCard
      className="ring-indigo-200"
      title={
        <>
          <Sparkles className="size-4 text-indigo-600" aria-hidden /> AI intelligence panel
        </>
      }
      action={<span className="text-xs font-semibold text-indigo-700">Advisory only. Cannot publish.</span>}
    >
      <div className="space-y-4">
        <AssessmentCards incident={i} />
        <dl className="grid gap-x-6 gap-y-4 border-t pt-4 sm:grid-cols-3">
          <div>
            <dt className="section-label">Extraction confidence</dt>
            <dd className="tnum mt-1 text-sm font-bold">{formatPercent(i.extractionConfidence)}</dd>
          </div>
          <div>
            <dt className="section-label">Matched blackspot</dt>
            <dd className="mt-1 text-sm font-bold">{nearest ? `${nearest.code} (demo)` : "None within 10 km"}</dd>
          </div>
          <div>
            <dt className="section-label">Provenance</dt>
            <dd className="mt-1 text-sm font-bold">
              {i.sourceCount} {i.sourceCount === 1 ? "source" : "sources"}, {i.verification === "corroborated" ? "corroborated" : "unverified"}
            </dd>
          </div>
          <div>
            <dt className="section-label">Suggested priority</dt>
            <dd className="mt-1">
              <PriorityBadge priority={i.reviewPriority} />
            </dd>
          </div>
        </dl>
      </div>
    </SectionCard>
  );
}

/* ------------------------------------------------------- editorial panel */

function LabeledSelect<T extends string>({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: readonly { value: T; label: string }[];
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={(v) => onChange(v as T)}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

const LOCATION_OPTIONS = (Object.keys(LOCATION_CONFIRMATION_LABEL) as LocationConfirmation[]).map((value) => ({
  value,
  label: LOCATION_CONFIRMATION_LABEL[value],
}));

function EditorPanel({ ws, onChanged }: { ws: ReviewWorkspace; onChanged: () => void }) {
  const i = ws.incident;
  const latest = ws.bulletins[0];
  const { user } = useDemoSession();
  const [headline, setHeadline] = useState(latest?.headline ?? i.title);
  const [body, setBody] = useState(latest?.body ?? "");
  const [notes, setNotes] = useState(ws.notes);
  const [incidentType, setIncidentType] = useState<IncidentType>(i.incidentType);
  const apiMode = getDataMode() === "api";
  const [pickedLocation, setLocation] = useState<LocationConfirmation>("unconfirmed");
  // In API mode the location comes from the server record, not from a local choice.
  const location: LocationConfirmation = apiMode
    ? i.locationInfo?.status === "editor_confirmed" ? "editor_confirmed" : "unconfirmed"
    : pickedLocation;
  const [fieldErrors, setFieldErrors] = useState<{ headline?: string; body?: string }>({});
  const [dialog, setDialog] = useState<"approve" | "reject" | "changes" | null>(null);
  const [pending, setPending] = useState<"save" | "approve" | "reject" | "changes" | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const textChanged = !latest || headline.trim() !== latest.headline || body.trim() !== latest.body;
  const dirty = textChanged || notes !== ws.notes;
  const canDecide = ws.canDecide;
  const checks = useMemo(() => checkBulletin(headline, body, location), [headline, body, location]);

  const editorName = user?.name ?? "you";
  const versionLabel = !textChanged && latest
    ? `Bulletin version ${latest.versionNumber} · ${latest.createdByName.replace(" (draft)", "")} ${latest.createdBy === "u-ai" ? "(AI draft)" : ""}`.trim()
    : `New bulletin version ${(latest?.versionNumber ?? 0) + 1} · edited by ${editorName}`;

  const decisionNotes = [
    notes.trim(),
    `Classification: ${INCIDENT_TYPE_LABEL[incidentType]}.`,
    `Location: ${LOCATION_CONFIRMATION_LABEL[location]}.`,
  ]
    .filter(Boolean)
    .join(" ");

  const handle = async (kind: NonNullable<typeof pending>, fn: () => Promise<{ message: string }>, after?: () => void) => {
    setPending(kind);
    setDialogError(null);
    setFieldErrors({});
    try {
      const result = await fn();
      toast.success(result.message);
      after?.();
      onChanged();
    } catch (error) {
      if (error instanceof ValidationError) {
        if (error.field === "headline" || error.field === "body") {
          setFieldErrors({ [error.field]: error.message });
          setDialog(null);
        } else {
          setDialogError(error.message);
        }
      } else {
        toast.error(errorMessage(error));
        setDialog(null);
      }
    } finally {
      setPending(null);
    }
  };

  const unconfirmedCasualties = !!ws.primaryEvent?.injuries;
  const chars = body.trim().length;

  return (
    <SectionCard
      className="ring-2 ring-slate-900"
      title={
        <>
          <PencilLine className="size-4" aria-hidden /> Editorial workspace
        </>
      }
      action={<span className="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white">Owned by the editor</span>}
    >
      <div className="space-y-5">
        <div className="space-y-1.5">
          <Label htmlFor="headline">Headline</Label>
          <Input
            id="headline"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            disabled={!canDecide}
            aria-invalid={!!fieldErrors.headline}
            aria-describedby={fieldErrors.headline ? "headline-err" : undefined}
          />
          {fieldErrors.headline ? <p id="headline-err" role="alert" className="text-xs font-medium text-red-700">{fieldErrors.headline}</p> : null}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="summary">Alert summary (what the public would read)</Label>
          <Textarea
            id="summary"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            disabled={!canDecide}
            aria-invalid={!!fieldErrors.body}
            aria-describedby="summary-help"
          />
          {fieldErrors.body ? <p role="alert" className="text-xs font-medium text-red-700">{fieldErrors.body}</p> : null}
          <p id="summary-help" className="tnum text-xs text-slate-600">
            {chars} characters
            {unconfirmedCasualties ? " · casualties are left out because they are not confirmed" : ""}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <LabeledSelect id="classification" label="Classification" value={incidentType} onChange={setIncidentType} options={INCIDENT_TYPE_OPTIONS} />
          {apiMode ? null : (
            <LabeledSelect id="location-confirmation" label="Location confirmation" value={location} onChange={setLocation} options={LOCATION_OPTIONS} />
          )}
        </div>
        {apiMode ? (
          <LocationPanel incident={i} canDecide={canDecide} onChanged={onChanged} />
        ) : (
          <p className="-mt-3 text-xs text-slate-600">Classification and location confirmation are recorded with your decision.</p>
        )}

        {i.point ? (
          <div>
            <h3 className="section-label mb-2">Location preview</h3>
            <div className="relative h-52">
              <SafetyMap
                incidents={[i]}
                layers={{ ...DEFAULT_LAYERS, blackspots: false }}
                selectedId={i.id}
                label={`Approximate position of ${i.referenceCode}`}
                className="h-full"
              />
              <span className="pointer-events-none absolute bottom-2 left-2 z-[500] rounded-md bg-white px-2 py-1 text-xs font-semibold shadow ring-1 ring-slate-300">
                Location: {location === "unconfirmed" ? "Unconfirmed" : LOCATION_CONFIRMATION_LABEL[location]}
              </span>
            </div>
          </div>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="notes">Editorial notes (internal, never published)</Label>
          <Textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="e.g. Called the police press office, awaiting confirmation"
            disabled={!canDecide}
          />
        </div>

        <details className="rounded-lg border bg-slate-50 px-4 py-3 text-sm">
          <summary className="cursor-pointer font-semibold">Public preview</summary>
          <div className="mt-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-xs font-semibold text-emerald-800">SafeRouteZW road alert{getDataMode() === "mock" ? " · demo" : ""}</p>
            <p className="mt-1 font-bold">{headline || "Headline"}</p>
            <p className="mt-1 leading-relaxed whitespace-pre-line">{body || "The alert summary will appear here."}</p>
            <p className="mt-2 text-xs text-slate-600">Verified by an editor. Reply STOP to unsubscribe.</p>
          </div>
        </details>

        {ws.bulletins.length > 0 ? (
          <details className="rounded-lg border px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold">Bulletin versions ({ws.bulletins.length})</summary>
            <ul className="mt-2 space-y-1.5">
              {ws.bulletins.map((b) => (
                <li key={b.id} className="tnum text-xs text-slate-700">
                  Version {b.versionNumber} · {b.createdByName} · {formatShort(b.createdAt)}
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <div className="border-t pt-5">
          {!canDecide ? (
            <ContextNote>Your role cannot record editorial decisions. Only editors and admins can approve, reject or request changes.</ContextNote>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              <Button
                variant="approve"
                size="lg"
                disabled={!!pending}
                onClick={() => {
                  setFieldErrors({});
                  setDialogError(null);
                  setDialog("approve");
                }}
              >
                <Check aria-hidden /> Approve
              </Button>
              <Button
                variant="outline"
                size="lg"
                disabled={!!pending || !dirty}
                onClick={() => handle("save", () => saveDraft(i.id, { headline, body, notes }))}
              >
                Save draft
              </Button>
              <Button variant="outline" size="lg" disabled={!!pending} onClick={() => { setDialogError(null); setDialog("changes"); }}>
                Request changes
              </Button>
              <Button variant="reject" size="lg" disabled={!!pending} onClick={() => { setDialogError(null); setDialog("reject"); }}>
                <X aria-hidden /> Reject
              </Button>
            </div>
          )}
          <p className="mt-3 text-xs text-slate-600">
            {getDataMode() === "mock"
              ? "Only a human can approve. Approval is simulated in this demo."
              : "Only a human can approve. The server checks your role before recording a decision."}
          </p>
          {dirty && canDecide ? <p className="mt-1 text-xs font-medium text-amber-800">You have unsaved changes.</p> : null}
        </div>
      </div>

      <ApproveDialog
        open={dialog === "approve"}
        onOpenChange={(o) => setDialog(o ? "approve" : null)}
        referenceCode={i.referenceCode}
        incidentType={incidentType}
        headline={headline.trim()}
        body={body.trim()}
        versionLabel={versionLabel}
        checks={checks}
        pending={pending === "approve"}
        onConfirm={() =>
          handle("approve", () => approveIncident(i.id, { headline, body, notes: decisionNotes }), () => setDialog(null))
        }
      />
      <RejectDialog
        open={dialog === "reject"}
        onOpenChange={(o) => setDialog(o ? "reject" : null)}
        pending={pending === "reject"}
        serverError={dialogError}
        onConfirm={(reason) => handle("reject", () => rejectIncident(i.id, reason), () => setDialog(null))}
      />
      <RequestChangesDialog
        open={dialog === "changes"}
        onOpenChange={(o) => setDialog(o ? "changes" : null)}
        pending={pending === "changes"}
        serverError={dialogError}
        onConfirm={(reason) => handle("changes", () => requestChanges(i.id, reason), () => setDialog(null))}
      />
    </SectionCard>
  );
}

/* --------------------------------------------------------- final decision */

function DecisionRecord({ ws }: { ws: ReviewWorkspace }) {
  const decision = ws.reviews[0];
  const approved = ws.state === "approved";
  const alerts = useResource(`review:${ws.incident.id}:alert`, () => listAlerts({ search: ws.incident.referenceCode, pageSize: 5 }));
  const alert = alerts.data?.items.find((a) => a.incidentId === ws.incident.id);
  return (
    <SectionCard
      title="Decision recorded"
      className={approved ? "ring-2 ring-emerald-600" : "ring-2 ring-slate-400"}
      action={<ReviewStateBadge state={ws.state} />}
    >
      <div className="space-y-3 text-sm">
        {decision ? (
          <p>
            {approved ? "Approved" : "Rejected"} by <strong>{decision.reviewerName}</strong> on{" "}
            <span className="tnum">{formatFull(decision.reviewedAt)}</span>.
          </p>
        ) : null}
        {decision?.notes ? (
          <blockquote className="border-l-4 border-slate-300 pl-3 text-slate-800">
            <q>{decision.notes}</q>
          </blockquote>
        ) : null}
        {approved ? (
          <>
            <ContextNote>Approval is not distribution. The approved bulletin has not necessarily reached any channel.</ContextNote>
            {alert ? (
              <Button asChild size="lg">
                <Link href={`/alerts/${alert.id}`}>View alert {alert.reference}</Link>
              </Button>
            ) : null}
          </>
        ) : (
          <p className="text-slate-600">This report was rejected and will not be shown on the map or shared.</p>
        )}
      </div>
    </SectionCard>
  );
}
