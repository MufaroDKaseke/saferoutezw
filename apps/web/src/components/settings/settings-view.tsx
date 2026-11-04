"use client";

import { useState } from "react";
import { Lock, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote } from "@/components/shared/notes";
import { SectionCard } from "@/components/shared/section-card";
import { Chip } from "@/components/shared/status";
import { useDemoSession } from "@/hooks/use-demo-session";
import { getDataMode } from "@/lib/api/config";
import { RELEVANCE_THRESHOLD } from "@/lib/domain/derive";
import { DEMO_MODEL_NAME } from "@/lib/mock/build";
import { resetMockDb } from "@/lib/mock/store";
import { cn } from "@/lib/utils";
import { REVIEWER_ROLES, type UserRole } from "@/types";

const SECTIONS = [
  { id: "account", label: "Account preferences" },
  { id: "theme", label: "Theme" },
  { id: "notifications", label: "Notifications" },
  { id: "polling", label: "RSS polling" },
  { id: "keywords", label: "Keyword filtering" },
  { id: "ai", label: "AI processing" },
  { id: "workflow", label: "Editorial workflow" },
  { id: "roles", label: "Roles and permissions" },
] as const;

function NotYet({ children = "Not available yet" }: { children?: React.ReactNode }) {
  return (
    <Chip tone="slate" icon={Lock}>
      {children}
    </Chip>
  );
}

function Row({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-1 border-b border-slate-100 py-3 last:border-0">
      <div className="min-w-0">
        <dt className="text-sm font-medium">{label}</dt>
        {hint ? <dd className="mt-0.5 max-w-md text-xs leading-relaxed text-slate-600">{hint}</dd> : null}
      </div>
      <dd className="text-sm font-semibold">{value}</dd>
    </div>
  );
}

const ROLE_ROWS: { role: UserRole; summary: string }[] = [
  { role: "admin", summary: "Manage sources and settings. May record editorial decisions." },
  { role: "editor", summary: "Review evidence and approve, reject or request changes." },
  { role: "contributor", summary: "Submit and annotate reports. Cannot record decisions." },
  { role: "service", summary: "Automated and AI accounts. Can draft, can never review." },
];

export function SettingsView() {
  const { user } = useDemoSession();
  const mock = getDataMode() === "mock";
  const [resetOpen, setResetOpen] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="How SafeRouteZW is set up. Anything the backend cannot change yet is shown read-only, so nothing here pretends to save."
      />

      <div className="grid items-start gap-8 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="lg:sticky lg:top-24">
          <ul className="flex flex-wrap gap-1.5 lg:flex-col lg:gap-0.5">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="block rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-950"
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-6">
          <SectionCard id="account" className="scroll-mt-24" title="Account preferences" description="Who you are signed in as">
            <dl>
              <Row label="Name" value={user?.name ?? "Not signed in"} />
              <Row label="Role" value={user ? user.role : "None"} hint="Your role is decided by the server. The browser only displays it." />
              <Row label="Email" value={user?.email ?? "None"} />
              <Row
                label="Session"
                value={user ? (user.isDemo ? <Chip tone="amber">Demo session</Chip> : <Chip tone="emerald">Signed in</Chip>) : <NotYet>Not signed in</NotYet>}
                hint="There is no authentication backend yet, so this is not a real sign-in."
              />
              <Row
                label="Data mode"
                value={<Chip tone={mock ? "amber" : "indigo"}>{mock ? "Demo data (mock)" : "Live API"}</Chip>}
                hint="Set with NEXT_PUBLIC_DATA_MODE. In API mode, pages show only what the backend provides."
              />
            </dl>
            {mock ? (
              <div className="mt-4 border-t pt-4">
                <Button variant="outline" size="lg" onClick={() => setResetOpen(true)}>
                  <RotateCcw aria-hidden /> Reset demo data
                </Button>
                <p className="mt-2 text-xs text-slate-600">Undoes every simulated approval, rejection, retry and source change made in this browser tab.</p>
              </div>
            ) : null}
          </SectionCard>

          <SectionCard id="theme" className="scroll-mt-24" title="Theme" description="Appearance">
            <dl>
              <Row label="Colour theme" value="Light" hint="A dark theme is planned in the design but has not been drawn, so it is not offered." />
            </dl>
          </SectionCard>

          <SectionCard
            id="notifications"
            className="scroll-mt-24"
            title="Notification preferences"
            description="What should interrupt you"
            action={<NotYet />}
          >
            <ul className="space-y-3">
              {["New high-priority reports", "Failed processing jobs", "Failed alert deliveries"].map((label) => (
                <li key={label} className="flex items-center justify-between gap-4 text-sm">
                  <span id={`pref-${label}`}>{label}</span>
                  <Switch disabled checked={false} aria-labelledby={`pref-${label}`} />
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-600">The header bell already lists items that need you, from live counts. Saved preferences need a settings API.</p>
          </SectionCard>

          <SectionCard id="polling" className="scroll-mt-24" title="RSS polling" description="How often feeds are checked" action={<NotYet>Read-only</NotYet>}>
            <dl>
              <Row label="Scheduler check" value="Every 3 minutes" hint="The scheduler looks for new articles. Individual sources can poll at their own interval on the Data Sources page." />
              <Row label="Polling and AI processing" value="Independent" hint="A slow AI step never delays feed polling, and the reverse." />
            </dl>
          </SectionCard>

          <SectionCard id="keywords" className="scroll-mt-24" title="Keyword filtering" description="Which articles are read further" action={<NotYet>Read-only</NotYet>}>
            <dl>
              <Row label="Relevance threshold" value={RELEVANCE_THRESHOLD.toFixed(2)} hint="Articles scoring below this are filtered out and never fetched in full." />
              <Row label="Ruleset" value="Zimbabwe road-safety keywords" hint="Incident, vehicle, road, place and traffic-impact terms. A match only means “read further”. It never means “verified”." />
            </dl>
          </SectionCard>

          <SectionCard id="ai" className="scroll-mt-24" title="AI processing" description="How articles become incident candidates" action={<NotYet>Read-only</NotYet>}>
            <dl>
              <Row label="Extraction model" value={mock ? DEMO_MODEL_NAME : "Reported by each extraction run"} hint="Each run records its own model name and version." />
              <Row label="Privacy redaction" value="Before every AI call" hint="Sender names and phone numbers are masked before text leaves the pipeline." />
              <Row label="Candidate threshold" value="0.50" hint="Events below this confidence are kept on the article but do not become incident candidates." />
              <Row label="API credentials" value="Never shown here" hint="Keys live on the server. The browser cannot read or change them." />
            </dl>
          </SectionCard>

          <SectionCard id="workflow" className="scroll-mt-24" title="Editorial workflow" description="Rules that cannot be switched off" action={<Chip tone="emerald" icon={Lock}>Fixed policy</Chip>}>
            <ul className="space-y-2.5 text-sm leading-relaxed">
              <li>Human editorial approval is mandatory. AI output can never publish anything.</li>
              <li>An approval applies to one exact bulletin version. Editing creates a new version that needs fresh approval.</li>
              <li>Decisions and bulletin versions are append-only and are never rewritten.</li>
              <li>Approval and delivery are separate. An approved bulletin has not necessarily reached any channel.</li>
            </ul>
          </SectionCard>

          <SectionCard id="roles" className="scroll-mt-24" title="Roles and permissions" description="Who can do what" action={<NotYet>Read-only</NotYet>}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[460px] text-sm">
                <caption className="sr-only">Roles and whether each can record editorial decisions</caption>
                <thead>
                  <tr className="border-b text-left text-[11.5px] font-semibold tracking-[0.06em] text-slate-500 uppercase">
                    <th scope="col" className="py-2 pr-3">Role</th>
                    <th scope="col" className="px-3 py-2">What it is for</th>
                    <th scope="col" className="py-2 pl-3">Can decide</th>
                  </tr>
                </thead>
                <tbody>
                  {ROLE_ROWS.map((r) => (
                    <tr key={r.role} className="border-b border-slate-100 align-top last:border-0">
                      <th scope="row" className="py-3 pr-3 text-left font-semibold capitalize">{r.role}</th>
                      <td className="px-3 py-3 text-slate-700">{r.summary}</td>
                      <td className={cn("py-3 pl-3 font-semibold", REVIEWER_ROLES.includes(r.role) ? "text-emerald-800" : "text-slate-600")}>
                        {REVIEWER_ROLES.includes(r.role) ? "Yes" : "No"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ContextNote className="mt-4">
              These rules are enforced by the server and the database. Hiding a button in the browser is never security,
              and roles cannot be changed from here.
            </ContextNote>
          </SectionCard>
        </div>
      </div>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset demo data?"
        description="Every simulated change returns to the original demo snapshot. Nothing outside this browser tab is affected."
        confirmLabel="Reset demo data"
        confirmVariant="reject"
        onConfirm={() => {
          resetMockDb();
          setResetOpen(false);
          toast.success("Demo data reset to the original snapshot.");
        }}
      />
    </div>
  );
}
