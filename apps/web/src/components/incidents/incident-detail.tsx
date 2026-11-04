"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ClipboardCheck, Sparkles } from "lucide-react";
import { BreadcrumbLabel } from "@/components/layout/breadcrumb-label";
import { SafetyMap } from "@/components/maps/safety-map-loader";
import { DEFAULT_LAYERS } from "@/components/maps/map-logic";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote } from "@/components/shared/notes";
import { ResourceView } from "@/components/shared/resource-view";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton } from "@/components/shared/states";
import { AiBadge, PriorityBadge, ReviewStateBadge, SeverityText, SyntheticBadge, VerificationBadge, AlertStateBadge } from "@/components/shared/status";
import { AuditTimeline } from "@/components/shared/timeline";
import { useResource } from "@/hooks/use-resource";
import { listAlerts } from "@/lib/api/alerts";
import { getIncident } from "@/lib/api/incidents";
import { formatFull, formatPercent, formatShort } from "@/lib/formatters/date";
import { ACCURACY_LABEL, INCIDENT_TYPE_LABEL, SEVERITY_LABEL } from "@/lib/formatters/labels";
import type { AuditEvent, IncidentDetail as IncidentDetailType } from "@/types";
import { AssessmentCards, EvidenceList, MissingInformation } from "./assessments";

export function IncidentDetail({ id }: { id: string }) {
  const data = useResource(`incident:${id}`, () => getIncident(id));
  return (
    <ResourceView resource={data} what="incident" skeleton={<CardBodySkeleton lines={10} />}>
      {({ incident, history }) => <IncidentView incident={incident} history={history} />}
    </ResourceView>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="section-label">{label}</dt>
      <dd className="mt-1 text-sm break-words">{children}</dd>
    </div>
  );
}

function IncidentView({ incident: i, history }: { incident: IncidentDetailType; history: AuditEvent[] }) {
  // An alert only exists after a human approval. Failure to load it must never hide the incident.
  const alerts = useResource(`incident:${i.id}:alert`, () => listAlerts({ search: i.referenceCode, pageSize: 5 }));
  const alert = alerts.data?.items.find((a) => a.incidentId === i.id);
  const open = i.reviewState === "pending" || i.reviewState === "needs_changes";
  const mapIncidents = useMemo(() => [i], [i]);
  const alertIds = useMemo(() => (alert ? [i.id] : []), [alert, i.id]);

  return (
    <div className="space-y-6">
      <BreadcrumbLabel path={`/incidents/${i.id}`} label={i.referenceCode} />
      <PageHeader
        meta={
          <>
            <span className="font-mono text-sm font-semibold">{i.referenceCode}</span>
            <ReviewStateBadge state={i.reviewState} />
            <VerificationBadge state={i.verification} />
            <PriorityBadge priority={i.reviewPriority} />
            {i.synthetic ? <SyntheticBadge /> : null}
          </>
        }
        title={i.title}
        description="Incident candidate to review. Not confirmed."
        actions={
          <>
            {open ? (
              <Button asChild size="lg">
                <Link href={`/reviews/${i.id}`}>
                  <ClipboardCheck aria-hidden /> Open review workspace
                </Link>
              </Button>
            ) : (
              <Button asChild variant="outline" size="lg">
                <Link href={`/reviews/${i.id}`}>View review record</Link>
              </Button>
            )}
            {alert ? (
              <Button asChild variant="outline" size="lg">
                <Link href={`/alerts/${alert.id}`}>View alert {alert.reference}</Link>
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <SectionCard
            title="Summary"
            description="Drafted by the AI for internal use. Not public text."
            action={<AiBadge />}
          >
            <p className="max-w-prose text-[15px] leading-relaxed">{i.summary}</p>
            <dl className="mt-5 grid gap-x-6 gap-y-4 border-t pt-5 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Event type">{INCIDENT_TYPE_LABEL[i.incidentType]}</Field>
              <Field label="Reported location">{i.locationText ?? "Not stated"}</Field>
              <Field label="Road">{i.roadName ?? "Not stated"}</Field>
              <Field label="Province">{i.province ?? "Not stated"}</Field>
              <Field label="Occurred">
                {i.occurredAt ? <span className="tnum">{formatFull(i.occurredAt)}</span> : "Not stated"}
                {i.occurredAtNote ? <span className="mt-0.5 block text-xs text-slate-600">{i.occurredAtNote}</span> : null}
              </Field>
              <Field label="Reported to SafeRouteZW">
                <span className="tnum">{formatFull(i.createdAt)}</span>
              </Field>
              <Field label="Vehicles">{i.vehicles.length ? i.vehicles.join(", ") : "None stated"}</Field>
              <Field label="Traffic impact">{i.trafficImpact ?? "None stated"}</Field>
              <Field label="Severity">
                <SeverityText severity={i.severity} prefix={false} />
                {i.severity !== "unknown" ? <span className="ml-1 text-xs text-slate-600">(suggested: {SEVERITY_LABEL[i.severity].toLowerCase()})</span> : null}
              </Field>
            </dl>
          </SectionCard>

          <SectionCard title="Assessments" description="Two separate questions, answered separately.">
            <AssessmentCards incident={i} />
          </SectionCard>

          <SectionCard
            title="Source articles"
            description={`${i.sourceCount} supporting ${i.sourceCount === 1 ? "article" : "articles"}. Each links to the full article and its AI extraction.`}
          >
            <EvidenceList evidence={i.evidence} />
          </SectionCard>

          <SectionCard
            title={
              <>
                <Sparkles className="size-4 text-indigo-600" aria-hidden /> AI extraction details
              </>
            }
            description="How the candidate was produced"
          >
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
              <Field label="Model">{i.extractionModel ?? "Not available"}</Field>
              <Field label="Model confidence">
                <span className="tnum">{formatPercent(i.extractionConfidence)}</span>{" "}
                <span className="text-xs text-slate-600">self-reported</span>
              </Field>
              <Field label="Editorial status">
                <ReviewStateBadge state={i.reviewState} />
              </Field>
            </dl>
            <ContextNote className="mt-4">
              Model confidence says how well fields were extracted from the text. It does not say the event is real.
            </ContextNote>
          </SectionCard>

          <SectionCard title="Missing information and uncertainty" description="Gaps an editor should weigh before deciding.">
            <MissingInformation items={i.missingInformation} />
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Location" description={i.point ? `${ACCURACY_LABEL[i.point.accuracy]}${i.point.synthetic ? " · illustrative demo position" : ""}` : "No position recorded"}>
            {i.point ? (
              <>
                <div className="h-72">
                  <SafetyMap
                    incidents={mapIncidents}
                    alertIncidentIds={alertIds}
                    layers={{ ...DEFAULT_LAYERS, blackspots: false }}
                    selectedId={i.id}
                    label={`Map showing the approximate position of ${i.referenceCode}`}
                    className="h-full"
                  />
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-600">
                  {i.point.accuracy === "exact" || i.point.accuracy === "road_segment"
                    ? "The position is good to a stretch of road."
                    : "The position is only approximate. Do not read it as the crash site."}
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-600">The article does not give enough to place this on a map.</p>
            )}
          </SectionCard>

          {alert ? (
            <SectionCard title="Public alert" description="Approval and delivery are separate.">
              <div className="space-y-2">
                <AlertStateBadge state={alert.publicationState} />
                <p className="text-sm">
                  <Link href={`/alerts/${alert.id}`} className="font-semibold text-emerald-800 hover:underline">
                    {alert.reference}
                  </Link>{" "}
                  approved by {alert.approvedByName} on <span className="tnum">{formatShort(alert.approvedAt)}</span>.
                </p>
              </div>
            </SectionCard>
          ) : null}

          <SectionCard title="Activity" description="Append-only record. Entries are never edited.">
            <AuditTimeline events={history} />
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
