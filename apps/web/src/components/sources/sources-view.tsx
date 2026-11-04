"use client";

import { useMemo, useState } from "react";
import { Activity, CheckCircle2, Database, FlaskConical, History, Pencil, Plus, TriangleAlert, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { KpiCard, KpiCardSkeleton } from "@/components/shared/kpi-card";
import { PageHeader } from "@/components/shared/page-header";
import { QueryError, EmptyState, TableSkeleton } from "@/components/shared/states";
import { Chip, ConnectionBadge, JobStatusBadge, SyntheticBadge } from "@/components/shared/status";
import { SimulationNote } from "@/components/shared/notes";
import { useResource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { getDataMode } from "@/lib/api/config";
import { listIngestionHistory, listSources, testSource, triggerPoll, updateSource } from "@/lib/api/sources";
import { formatDuration, formatInterval, formatRelative, formatShort } from "@/lib/formatters/date";
import { SOURCE_KIND_LABEL, TIER_LABEL } from "@/lib/formatters/labels";
import type { IngestionRun, SourceSummary } from "@/types";
import { SourceFormDialog } from "./source-form-dialog";

const helper = columnHelper<SourceSummary>();

export function SourcesView() {
  const sources = useResource("sources:list", () => listSources());
  const [form, setForm] = useState<{ open: boolean; source: SourceSummary | null }>({ open: false, source: null });
  const [history, setHistory] = useState<SourceSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ source: SourceSummary; ok: boolean; message: string } | null>(null);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    try {
      await action();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const columns = useMemo(
    () => [
      helper.display({
        id: "name",
        header: "Publisher",
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-sm font-semibold">
              {row.original.name}
              {row.original.synthetic ? <SyntheticBadge /> : null}
            </p>
            <p className="text-xs text-slate-600">
              {SOURCE_KIND_LABEL[row.original.kind]} · {TIER_LABEL[row.original.verificationTier]}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "url",
        header: "RSS URL",
        cell: ({ row }) => (
          <span className="block max-w-36 truncate font-mono text-xs text-slate-700" title={row.original.feedUrl ?? undefined}>
            {row.original.feedUrl?.replace(/^https?:\/\//, "") ?? "None"}
          </span>
        ),
      }),
      helper.display({
        id: "enabled",
        header: "Polling",
        cell: ({ row }) => (
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={row.original.enabled}
              disabled={busy === `toggle:${row.original.id}`}
              aria-label={`${row.original.enabled ? "Disable" : "Enable"} ${row.original.name}`}
              onCheckedChange={(checked) =>
                run(`toggle:${row.original.id}`, async () => {
                  const result = await updateSource(row.original.id, { enabled: checked });
                  toast.success(result.message);
                })
              }
            />
            <span className="text-xs text-slate-700">
              {row.original.enabled ? `Every ${formatInterval(row.original.pollIntervalSeconds)}` : "Paused"}
            </span>
          </label>
        ),
      }),
      helper.display({
        id: "polls",
        header: "Last poll / last success",
        cell: ({ row }) => (
          <div className="tnum text-sm">
            <p>{row.original.lastPollAt ? formatShort(row.original.lastPollAt) : "Never"}</p>
            <p className="text-xs text-slate-600">
              {row.original.lastSuccessfulPollAt ? `Success ${formatRelative(row.original.lastSuccessfulPollAt)}` : "No success yet"}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "discovered",
        header: "Articles / errors",
        cell: ({ row }) => (
          <div className="tnum text-sm">
            <p className="font-medium">{row.original.articlesDiscovered} articles</p>
            <p className={row.original.errorCount > 0 ? "text-xs font-medium text-red-800" : "text-xs text-slate-600"}>
              {row.original.errorCount} {row.original.errorCount === 1 ? "error" : "errors"}
            </p>
          </div>
        ),
      }),
      helper.display({
        id: "status",
        header: "Connection",
        cell: ({ row }) => (
          <div className="space-y-1">
            <ConnectionBadge status={row.original.connectionStatus} />
            {row.original.lastError ? (
              <p className="max-w-52 text-xs leading-snug text-red-800">{row.original.lastError}</p>
            ) : null}
          </div>
        ),
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const s = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="icon"
                disabled={busy === `test:${s.id}`}
                aria-label={`Test connection: ${s.name}`}
                title="Test connection"
                onClick={() =>
                  run(`test:${s.id}`, async () => {
                    const result = await testSource(s.id);
                    setTestResult({ source: s, ok: result.data?.ok ?? false, message: result.data?.message ?? result.message });
                  })
                }
              >
                <FlaskConical aria-hidden />
              </Button>
              <Button
                variant="outline"
                size="icon"
                disabled={!s.enabled || busy === `poll:${s.id}`}
                aria-label={`Poll now: ${s.name}`}
                title={s.enabled ? "Poll now" : "Enable the source to poll it"}
                onClick={() =>
                  run(`poll:${s.id}`, async () => {
                    const result = await triggerPoll(s.id);
                    toast.success(result.message);
                  })
                }
              >
                <Zap aria-hidden />
              </Button>
              <Button variant="outline" size="icon" aria-label={`Ingestion history: ${s.name}`} title="Ingestion history" onClick={() => setHistory(s)}>
                <History aria-hidden />
              </Button>
              <Button variant="outline" size="icon" aria-label={`Edit ${s.name}`} title="Edit source" onClick={() => setForm({ open: true, source: s })}>
                <Pencil aria-hidden />
              </Button>
            </div>
          );
        },
      }),
    ],
    [busy],
  );

  const data = sources.data;
  const enabled = data?.filter((s) => s.enabled).length ?? 0;
  const healthy = data?.filter((s) => s.connectionStatus === "healthy").length ?? 0;
  const attention = data?.filter((s) => s.connectionStatus === "failing" || s.connectionStatus === "degraded").length ?? 0;
  const discovered = data?.reduce((n, s) => n + s.articlesDiscovered, 0) ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data Sources"
        description="The sources SafeRouteZW reads."
        actions={
          <Button size="lg" onClick={() => setForm({ open: true, source: null })}>
            <Plus aria-hidden /> Add RSS feed
          </Button>
        }
      />

      {getDataMode() === "mock" ? (
        <SimulationNote>
          These are fictional demo feeds on reserved <code className="font-mono text-xs">.example</code> addresses.
          Testing, polling and editing change the demo only. No network request is made.
        </SimulationNote>
      ) : null}

      <section aria-label="Source summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {!data ? (
          Array.from({ length: 4 }, (_, i) => <KpiCardSkeleton key={i} />)
        ) : (
          <>
            <KpiCard title="Sources" value={data.length} icon={Database} hint={`${enabled} enabled`} />
            <KpiCard title="Healthy" value={healthy} icon={CheckCircle2} tone="emerald" hint="Recent polls succeeded" />
            <KpiCard
              title="Need attention"
              value={attention}
              icon={TriangleAlert}
              tone={attention ? "red" : "slate"}
              emphasis={attention > 0}
              hint={attention ? <strong className="text-red-800">Failing or degraded feeds</strong> : "None"}
            />
            <KpiCard title="Articles discovered" value={discovered} icon={Activity} hint="Across all sources" />
          </>
        )}
      </section>

      <Card className="gap-0 overflow-hidden py-0">
        {sources.error ? (
          <QueryError error={sources.error} onRetry={sources.refetch} />
        ) : sources.isLoading ? (
          <TableSkeleton cols={8} />
        ) : (
          <DataTable
            caption="Configured RSS sources"
            columns={columns}
            data={data ?? []}
            getRowId={(s) => s.id}
            total={data?.length ?? 0}
            page={1}
            pageSize={50}
            onPageChange={() => {}}
            noun={["source", "sources"]}
            isFetching={sources.isFetching}
            minWidth={940}
            columnClassName={{ name: "min-w-48", actions: "w-44" }}
            empty={
              <EmptyState
                title="No sources yet"
                description="Add an RSS feed to start collecting articles."
                action={
                  <Button onClick={() => setForm({ open: true, source: null })}>
                    <Plus aria-hidden /> Add RSS feed
                  </Button>
                }
              />
            }
          />
        )}
      </Card>

      <SourceFormDialog open={form.open} onOpenChange={(open) => setForm((f) => ({ ...f, open }))} source={form.source} />
      <HistoryDialog source={history} onClose={() => setHistory(null)} />

      <Dialog open={!!testResult} onOpenChange={(open) => (!open ? setTestResult(null) : undefined)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connection test: {testResult?.source.name}</DialogTitle>
            <DialogDescription>{getDataMode() === "mock" ? "Simulated. No network request was made." : "Result of a live check."}</DialogDescription>
          </DialogHeader>
          <p
            role="status"
            className={testResult?.ok ? "rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950" : "rounded-lg bg-red-50 p-3 text-sm text-red-950"}
          >
            <strong>{testResult?.ok ? "Reachable. " : "Not reachable. "}</strong>
            {testResult?.message}
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function HistoryDialog({ source, onClose }: { source: SourceSummary | null; onClose: () => void }) {
  return (
    <Dialog open={!!source} onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Ingestion history: {source?.name}</DialogTitle>
          <DialogDescription>The most recent polling runs, newest first.</DialogDescription>
        </DialogHeader>
        {source ? <HistoryTable sourceId={source.id} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function HistoryTable({ sourceId }: { sourceId: string }) {
  const runs = useResource(`sources:history:${sourceId}`, () => listIngestionHistory(sourceId));
  if (runs.error) return <QueryError error={runs.error} onRetry={runs.refetch} />;
  if (!runs.data) return <TableSkeleton cols={5} rows={5} />;
  if (runs.data.length === 0) return <EmptyState title="No runs recorded" description="This source has not been polled yet." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <caption className="sr-only">Polling runs</caption>
        <thead>
          <tr className="border-b text-left text-[11.5px] font-semibold tracking-[0.06em] text-slate-500 uppercase">
            <th scope="col" className="py-2 pr-3">Started</th>
            <th scope="col" className="px-3 py-2">Result</th>
            <th scope="col" className="px-3 py-2">Fetched</th>
            <th scope="col" className="px-3 py-2">New</th>
            <th scope="col" className="px-3 py-2">Duration</th>
          </tr>
        </thead>
        <tbody>
          {runs.data.map((r: IngestionRun) => (
            <tr key={r.id} className="border-b border-slate-100 align-top last:border-0">
              <td className="tnum py-2.5 pr-3">
                {formatShort(r.startedAt)}
                <span className="block text-xs text-slate-600">
                  {r.trigger === "manual" ? "Manual" : "Scheduled"}
                  {r.simulated ? " (simulated)" : ""}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <JobStatusBadge status={r.status === "running" ? "running" : r.status} />
                {r.errorMessage ? <p className="mt-1 max-w-64 text-xs text-red-800">{r.errorMessage}</p> : null}
              </td>
              <td className="tnum px-3 py-2.5">{r.fetchedCount}</td>
              <td className="tnum px-3 py-2.5">{r.insertedCount}</td>
              <td className="tnum px-3 py-2.5">
                {r.completedAt ? formatDuration(new Date(r.completedAt).getTime() - new Date(r.startedAt).getTime()) : "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-slate-600">
        <Chip tone="slate">Last {runs.data.length} runs</Chip>
      </p>
    </div>
  );
}
