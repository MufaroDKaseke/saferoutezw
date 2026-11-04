"use client";

import Link from "next/link";
import { useState } from "react";
import { RotateCw, Send } from "lucide-react";
import { toast } from "sonner";
import { BreadcrumbLabel } from "@/components/layout/breadcrumb-label";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote, SimulationNote } from "@/components/shared/notes";
import { ResourceView } from "@/components/shared/resource-view";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton } from "@/components/shared/states";
import { AlertStateBadge, ChannelStatusBadge, SyntheticBadge } from "@/components/shared/status";
import { useResource } from "@/hooks/use-resource";
import { getAlert, publishAlert, retryDelivery } from "@/lib/api/alerts";
import { getDataMode } from "@/lib/api/config";
import { errorMessage } from "@/lib/api/errors";
import { getIncident } from "@/lib/api/incidents";
import { formatFull, formatShort } from "@/lib/formatters/date";
import { CHANNEL_LABEL, INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import type { ChannelDelivery, ChannelKind, PublicAlert } from "@/types";

export function AlertDetail({ id }: { id: string }) {
  const alert = useResource(`alert:${id}`, () => getAlert(id));
  return (
    <ResourceView resource={alert} what="alert" skeleton={<CardBodySkeleton lines={10} />}>
      {(a) => <AlertView alert={a} />}
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

function AlertView({ alert: a }: { alert: PublicAlert }) {
  const mock = getDataMode() === "mock";
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<{ message: string }>) => {
    setBusy(key);
    try {
      const result = await fn();
      toast.success(result.message);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <BreadcrumbLabel path={`/alerts/${a.id}`} label={a.reference} />
      <PageHeader
        meta={
          <>
            <span className="font-mono text-sm font-semibold">{a.reference}</span>
            <AlertStateBadge state={a.publicationState} />
            {a.synthetic ? <SyntheticBadge /> : null}
          </>
        }
        title={a.headline}
        description="An approved bulletin. Approval says an editor signed off the wording; delivery is tracked separately for each channel."
        actions={
          <Button asChild variant="outline" size="lg">
            <Link href={`/incidents/${a.incidentId}`}>View incident {a.incidentReference}</Link>
          </Button>
        }
      />

      {mock ? (
        <SimulationNote>
          <strong>Simulation.</strong> Nothing is really sent. Buttons on this page only change the demo.
        </SimulationNote>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <SectionCard title="Approved bulletin" description={`Version ${a.bulletinVersionNumber}, exactly as approved`}>
            <article className="rounded-xl border bg-slate-50 p-4">
              <h3 className="text-base leading-snug font-bold">{a.headline}</h3>
              <p className="mt-2 text-sm leading-relaxed whitespace-pre-line">{a.body}</p>
            </article>
            <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Field label="Linked incident">
                <Link href={`/incidents/${a.incidentId}`} className="font-semibold text-emerald-800 hover:underline">
                  {a.incidentReference}
                </Link>{" "}
                · {INCIDENT_TYPE_LABEL[a.incidentType]}
              </Field>
              <Field label="Location">{a.locationText ?? "Not stated"}</Field>
              <Field label="Approved by">{a.approvedByName}</Field>
              <Field label="Approved at">
                <span className="tnum">{formatFull(a.approvedAt)}</span>
              </Field>
              <Field label="Bulletin version">Version {a.bulletinVersionNumber}</Field>
              <Field label="Publication">
                {a.publishedAt ? <span className="tnum">{formatFull(a.publishedAt)}</span> : "Not published yet"}
              </Field>
            </dl>
          </SectionCard>

          <SectionCard title="What each channel receives" description="Public channels never include unverified details, sender information or internal notes.">
            <ChannelPreviews alert={a} />
          </SectionCard>
        </div>

        <SectionCard title="Delivery" description="One row per channel. A failure on one channel does not affect the others.">
          {a.channels.length === 0 ? (
            <div className="space-y-4">
              <p className="text-sm leading-relaxed">
                This bulletin is <strong>approved but has not been sent</strong> to any channel.
              </p>
              <Button
                size="lg"
                disabled={busy === "publish" || a.status !== "ready"}
                onClick={() => run("publish", () => publishAlert(a.id))}
              >
                <Send aria-hidden /> {mock ? "Publish (simulated)" : "Publish"}
              </Button>
              <ContextNote>
                Publishing is a separate, protected action. {mock ? "In this demo it only marks the alert as published." : "The server decides whether it may proceed."}
              </ContextNote>
            </div>
          ) : (
            <ul className="space-y-4">
              {a.channels.map((c) => (
                <ChannelCard
                  key={c.channel}
                  channel={c}
                  busy={busy === `retry:${c.channel}`}
                  onRetry={() => run(`retry:${c.channel}`, () => retryDelivery(a.id, c.channel))}
                />
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </div>
  );
}

function ChannelCard({ channel: c, busy, onRetry }: { channel: ChannelDelivery; busy: boolean; onRetry: () => void }) {
  const canRetry = c.status === "failed" && c.attempts.length < c.maxAttempts;
  const mock = getDataMode() === "mock";
  return (
    <li className="rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <h3 className="text-sm font-bold">{CHANNEL_LABEL[c.channel]}</h3>
          <ChannelStatusBadge status={c.status} channel={c.channel} />
          <span className="tnum text-xs text-slate-600">
            {c.attempts.length} of {c.maxAttempts} attempts
          </span>
        </div>
        {canRetry ? (
          <Button variant="reject" disabled={busy} onClick={onRetry}>
            <RotateCw aria-hidden /> Retry {CHANNEL_LABEL[c.channel]}
            {mock ? " (simulated)" : ""}
          </Button>
        ) : null}
      </div>
      {c.lastError && c.status === "failed" ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-950">
          <strong>Delivery failed.</strong> {c.lastError}. The other channels were not affected.
        </p>
      ) : null}
      <ol className="mt-3 space-y-1.5">
        {c.attempts.map((t) => (
          <li key={t.id} className="tnum flex flex-wrap items-baseline gap-x-3 text-xs text-slate-700">
            <span className="font-medium">Attempt {t.attemptNumber}</span>
            <span>{formatShort(t.attemptedAt)}</span>
            <span className={t.status === "succeeded" ? "text-emerald-800" : "text-red-800"}>
              {t.status === "succeeded" ? "Succeeded" : `Failed${t.error ? `: ${t.error}` : ""}`}
            </span>
          </li>
        ))}
      </ol>
      {c.status === "failed" && !canRetry ? (
        <p className="mt-2 text-xs text-slate-600">All attempts have been used. An administrator must investigate.</p>
      ) : null}
    </li>
  );
}

/* ---------------------------------------------------------------- previews */

function smsText(a: PublicAlert) {
  const text = `SafeRouteZW: ${a.headline}. ${a.body} Reply STOP to opt out.`;
  return text.replace(/\s+/g, " ");
}

function ChannelPreviews({ alert: a }: { alert: PublicAlert }) {
  const incident = useResource(`alert:${a.id}:incident`, () => getIncident(a.incidentId));
  const point = incident.data?.incident.point ?? null;
  const sms = smsText(a);
  const segments = Math.ceil(sms.length / 160);
  const mock = getDataMode() === "mock";

  const geojson = JSON.stringify(
    {
      type: "Feature",
      properties: {
        reference: a.reference,
        headline: a.headline,
        summary: a.body,
        incident_type: a.incidentType,
        approved_at: a.approvedAt,
        position_accuracy: point?.accuracy ?? null,
      },
      geometry: point ? { type: "Point", coordinates: [point.lng, point.lat] } : null,
    },
    null,
    2,
  );

  const tabs: { value: string; label: string; channel: ChannelKind }[] = [
    { value: "whatsapp", label: "WhatsApp", channel: "whatsapp" },
    { value: "sms", label: "SMS", channel: "sms" },
    { value: "geojson", label: "GeoJSON API", channel: "web" },
    { value: "embed", label: "Embed", channel: "web" },
  ];

  return (
    <Tabs defaultValue="whatsapp" className="gap-4">
      <TabsList className="h-auto flex-wrap justify-start">
        {tabs.map((t) => (
          <TabsTrigger key={t.value} value={t.value} className="h-9 px-3.5">
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>

      <TabsContent value="whatsapp">
        <div className="rounded-xl bg-slate-200/70 p-4">
          <div className="max-w-sm rounded-xl bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold text-emerald-800">SafeRouteZW road alert{mock ? " · demo" : ""}</p>
            <p className="mt-1 text-[15px] font-bold">{a.headline}</p>
            <p className="mt-1 text-sm leading-relaxed">{a.body}</p>
            <p className="mt-2 text-xs text-slate-600">Verified by an editor. Reply STOP to unsubscribe.</p>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="sms">
        <div className="space-y-2">
          <p className="rounded-xl bg-slate-100 p-4 font-mono text-sm leading-relaxed break-words">{sms}</p>
          <p className="tnum text-xs text-slate-600">
            {sms.length} characters · {segments} {segments === 1 ? "message" : "messages"} (160 per message)
          </p>
        </div>
      </TabsContent>

      <TabsContent value="geojson">
        <pre className="max-h-80 overflow-auto rounded-xl bg-slate-900 p-4 text-xs leading-relaxed text-slate-100" tabIndex={0} aria-label="GeoJSON feature">
          <code>{geojson}</code>
        </pre>
        <p className="mt-2 text-xs text-slate-600">
          {point
            ? `The position is ${point.accuracy === "exact" ? "exact" : "approximate"}${point.synthetic ? " and synthetic (demo)" : ""}. Consumers should not treat it as the crash site.`
            : "No position is published because none is recorded."}
        </p>
      </TabsContent>

      <TabsContent value="embed">
        <div className="rounded-xl border-l-4 border-emerald-600 bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <p className="text-xs font-semibold text-emerald-800">SafeRouteZW alert {a.reference}</p>
          <p className="mt-1 font-bold">{a.headline}</p>
          <p className="mt-1 text-sm leading-relaxed">{a.body}</p>
          <p className="tnum mt-2 text-xs text-slate-600">Approved {formatShort(a.approvedAt)} by an editor</p>
        </div>
      </TabsContent>
    </Tabs>
  );
}
