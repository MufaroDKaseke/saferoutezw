import Link from "next/link";
import { ContextNote } from "@/components/shared/notes";
import { SegmentMeter } from "@/components/shared/meter";
import { Chip } from "@/components/shared/status";
import { credibilityLevel, scoreSegments } from "@/lib/domain/derive";
import { formatShort } from "@/lib/formatters/date";
import { CREDIBILITY_LABEL, EVIDENCE_ROLE_LABEL, RISK_LABEL } from "@/lib/formatters/labels";
import { cn } from "@/lib/utils";
import type { IncidentDetail, IncidentEvidence } from "@/types";

/**
 * Credibility and geographic risk answer different questions, so they are two
 * separate assessments. A blackspot match is background, never evidence.
 */
export function AssessmentCards({ incident, className }: { incident: IncidentDetail; className?: string }) {
  const level = credibilityLevel(incident.credibilityScore);
  const nearest = incident.blackspotMatches[0];
  return (
    <div className={cn("space-y-3", className)}>
      <div className="grid gap-3 sm:grid-cols-2">
        <section className="rounded-xl border bg-card p-4" aria-label="Incident credibility">
          <h3 className="section-label">Incident credibility</h3>
          <p className="mt-1 text-xs text-slate-600">How well the evidence supports that this event happened.</p>
          <SegmentMeter className="mt-3" filled={scoreSegments(incident.credibilityScore)} label="Credibility" />
          <p className="mt-2 text-lg font-bold">{level ? CREDIBILITY_LABEL[level] : "Not assessed"}</p>
          {incident.credibilityRationale ? <p className="mt-1 text-xs leading-relaxed text-slate-600">{incident.credibilityRationale}</p> : null}
        </section>
        <section className="rounded-xl border bg-card p-4" aria-label="Geographic risk">
          <h3 className="section-label">Geographic risk</h3>
          <p className="mt-1 text-xs text-slate-600">How relevant the place is to known historical hazards.</p>
          <SegmentMeter className="mt-3" tone="red" filled={scoreSegments(incident.geographicRiskScore)} label="Geographic risk" />
          <p className="mt-2 text-lg font-bold">{incident.riskLevel ? RISK_LABEL[incident.riskLevel] : "Not assessed"}</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            {nearest
              ? `About ${nearest.distanceKm} km from demo blackspot ${nearest.code} on this road.`
              : "No demo blackspot within 10 km. The score reflects corridor-level history only."}
          </p>
        </section>
      </div>
      <ContextNote>A blackspot match is background context. It is never evidence that this accident happened.</ContextNote>
    </div>
  );
}

/** Source articles that support (or contradict) an incident. One article can appear on several incidents. */
export function EvidenceList({ evidence }: { evidence: IncidentEvidence[] }) {
  if (evidence.length === 0) return <p className="text-sm text-slate-600">No source articles are linked yet.</p>;
  return (
    <ul className="space-y-3">
      {evidence.map((e) => (
        <li key={e.id} className="rounded-lg border p-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={e.role === "primary" ? "slate" : "emerald"} className={e.role === "primary" ? "bg-slate-900 text-white" : undefined}>
              {EVIDENCE_ROLE_LABEL[e.role]}
            </Chip>
            <span className="tnum text-xs text-slate-600">
              {e.publisherName} · {formatShort(e.publishedAt)}
            </span>
          </div>
          <Link href={`/news/${e.sourceItemId}`} className="mt-1.5 block text-sm leading-snug font-semibold hover:underline">
            {e.articleTitle}
          </Link>
          {e.snippet ? (
            <blockquote className="mt-2 border-l-4 border-indigo-200 pl-3 text-sm text-slate-800">
              <q>{e.snippet}</q>
            </blockquote>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function MissingInformation({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-600">Nothing important is missing. The evidence covers place, time and effect.</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((m) => (
        <li key={m} className="flex gap-2.5 text-sm leading-snug">
          <span className="mt-0.5 h-fit shrink-0 rounded border border-amber-400 bg-white px-1.5 py-px text-[10px] font-bold text-amber-800">GAP</span>
          {m}
        </li>
      ))}
    </ul>
  );
}
