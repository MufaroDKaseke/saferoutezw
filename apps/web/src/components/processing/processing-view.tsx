"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, Cpu, FileText, Hourglass, ListFilter, RotateCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { columnHelper, DataTable } from "@/components/shared/data-table";
import { FilterBar, RANGE_OPTIONS, SearchField, SelectField } from "@/components/shared/filters";
import { KpiCard, KpiCardSkeleton } from "@/components/shared/kpi-card";
import { PageHeader } from "@/components/shared/page-header";
import { ContextNote, SimulationNote } from "@/components/shared/notes";
import { SegmentedControl } from "@/components/shared/segmented";
import { EmptyState, QueryError } from "@/components/shared/states";
import { Chip, JobStatusBadge } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { errorMessage } from "@/lib/api/errors";
import { getBacklog, listProcessing, retryJob } from "@/lib/api/processing";
import { listSources } from "@/lib/api/sources";
import type { DateRangeKey } from "@/lib/api/types";
import { formatDuration, formatFull, formatShort } from "@/lib/formatters/date";
import { JOB_KIND_LABEL, JOB_STATUS_LABEL } from "@/lib/formatters/labels";
import type { ProcessingJob, ProcessingJobKind, ProcessingJobStatus } from "@/types";

const helper = columnHelper<ProcessingJob>();

type KindFilter = "all" | ProcessingJobKind;

const KIND_TABS: { value: KindFilter; label: string }[] = [
  { value: "all", label: "All activity" },
  { value: "rss_poll", label: "RSS polling" },
  { value: "keyword_screening", label: "Keyword screening" },
  { value: "article_retrieval", label: "Article retrieval" },
  { value: "ai_extraction", label: "AI extraction" },
];

const STATUS_OPTIONS = (Object.keys(JOB_STATUS_LABEL) as ProcessingJobStatus[]).map((value) => ({
  value,
  label: JOB_STATUS_LABEL[value],
}));

const PAGE_SIZE = 12;

export function ProcessingView() {
  const list = useListState({
    search: "",
    kind: "all" as KindFilter,
    status: undefined as ProcessingJobStatus | undefined,
    sourceId: undefined as string | undefined,
    range: undefined as DateRangeKey | undefined,
  });
  const { filters } = list;
  const search = useDebouncedValue(filters.search);
  const [selected, setSelected] = useState<ProcessingJob | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);

  const sources = useResource("processing:sources", () => listSources());
  const backlog = useResource("processing:backlog", () => getBacklog());
  const query = {
    search,
    kind: filters.kind === "all" ? undefined : filters.kind,
    status: filters.status,
    sourceId: filters.sourceId,
    range: filters.range,
    page: list.page,
    pageSize: PAGE_SIZE,
  };
  const jobs = useResource(`processing:${JSON.stringify(query)}`, () => listProcessing(query));

  const retry = async (job: ProcessingJob) => {
    setRetrying(job.id);
    try {
      const result = await retryJob(job.id);
      toast.success(result.message);
      setSelected(null);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setRetrying(null);
    }
  };

  const columns = useMemo(
    () => [
      helper.display({
        id: "time",
        header: "Started",
        cell: ({ row }) => <span className="tnum text-sm whitespace-nowrap">{formatShort(row.original.startedAt)}</span>,
      }),
      helper.display({
        id: "kind",
        header: "Stage",
        cell: ({ row }) => (
          <Chip tone={row.original.kind === "ai_extraction" ? "indigo" : "slate"}>{JOB_KIND_LABEL[row.original.kind]}</Chip>
        ),
      }),
      helper.display({
        id: "subject",
        header: "What was processed",
        cell: ({ row }) => (
          <div className="min-w-0">
            {row.original.sourceItemId ? (
              <Link href={`/news/${row.original.sourceItemId}`} className="text-sm leading-snug font-semibold hover:underline">
                {row.original.subject}
              </Link>
            ) : (
              <p className="text-sm font-semibold">{row.original.subject}</p>
            )}
            <p className="text-xs text-slate-600">{row.original.sourceName}</p>
          </div>
        ),
      }),
      helper.display({
        id: "status",
        header: "Status",
        cell: ({ row }) => (
          <div className="space-y-1">
            <JobStatusBadge status={row.original.status} />
            {row.original.simulated ? <p className="text-xs text-amber-800">Simulated</p> : null}
          </div>
        ),
      }),
      helper.display({
        id: "duration",
        header: "Duration",
        cell: ({ row }) => <span className="tnum text-sm">{formatDuration(row.original.durationMs)}</span>,
      }),
      helper.display({
        id: "details",
        header: "Result",
        cell: ({ row }) => (
          <div className="max-w-72 text-sm">
            <p className="leading-snug">{row.original.summary}</p>
            {row.original.errorMessage ? <p className="mt-0.5 text-xs leading-snug text-red-800">{row.original.errorMessage}</p> : null}
            {row.original.retryCount > 0 ? (
              <p className="mt-0.5 text-xs text-slate-600">
                {row.original.retryCount} {row.original.retryCount === 1 ? "retry" : "retries"} so far
              </p>
            ) : null}
          </div>
        ),
      }),
      helper.display({
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1.5">
            {row.original.status === "failed" || row.original.errorMessage ? (
              <Button variant="outline" size="sm" onClick={() => setSelected(row.original)}>
                Details<span className="sr-only"> for {row.original.subject}</span>
              </Button>
            ) : null}
            {row.original.retryable ? (
              <Button variant="outline" size="sm" disabled={retrying === row.original.id} onClick={() => retry(row.original)}>
                <RotateCw aria-hidden /> Retry
              </Button>
            ) : null}
          </div>
        ),
      }),
    ],
    [retrying],
  );

  const b = backlog.data;
  const data = jobs.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Processing Activity"
        description="What the pipeline has done and what is still waiting. Scheduled RSS polling and AI processing are separate jobs, so a feed can be healthy while extraction is behind."
      />

      {getDataMode() === "mock" ? (
        <SimulationNote>
          Demo history. Retrying here only queues a labelled, simulated retry. No feed is fetched and no AI call is made.
        </SimulationNote>
      ) : null}

      <section aria-label="Waiting to be processed" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {backlog.error ? (
          <div className="sm:col-span-2 xl:col-span-4">
            <QueryError error={backlog.error} onRetry={backlog.refetch} />
          </div>
        ) : !b ? (
          Array.from({ length: 4 }, (_, i) => <KpiCardSkeleton key={i} />)
        ) : (
          <>
            <KpiCard title="Awaiting keyword screening" value={b.awaitingScreening} icon={ListFilter} hint="Newly ingested articles" />
            <KpiCard title="Awaiting full text" value={b.awaitingFullText} icon={FileText} tone="amber" hint="Retrieval is queued" />
            <KpiCard title="Awaiting AI extraction" value={b.awaitingExtraction} icon={Hourglass} tone="indigo" hint="Independent of RSS polling" />
            <KpiCard
              title="Failed, needs attention"
              value={b.failedNeedingAttention}
              icon={AlertTriangle}
              tone={b.failedNeedingAttention ? "red" : "slate"}
              emphasis={b.failedNeedingAttention > 0}
              hint={b.failedNeedingAttention ? <strong className="text-red-800">Retry or inspect</strong> : "Nothing failed"}
            />
          </>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Pipeline stage"
          value={filters.kind}
          onChange={(v) => list.setFilter("kind", v)}
          options={KIND_TABS}
          className="max-w-full overflow-x-auto"
        />
      </div>

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField label="Search" value={filters.search} onChange={(v) => list.setFilter("search", v)} placeholder="Headline, source or error" className="lg:col-span-2" />
        <SelectField label="Status" value={filters.status} onChange={(v) => list.setFilter("status", v)} options={STATUS_OPTIONS} allLabel="All statuses" />
        <SelectField
          label="Source"
          value={filters.sourceId}
          onChange={(v) => list.setFilter("sourceId", v)}
          options={(sources.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
          allLabel="All sources"
        />
        <SelectField label="Date" value={filters.range} onChange={(v) => list.setFilter("range", v)} options={RANGE_OPTIONS} allLabel="Any time" />
      </FilterBar>

      <Card className="gap-0 overflow-hidden py-0">
        {jobs.error ? (
          <QueryError error={jobs.error} onRetry={jobs.refetch} />
        ) : (
          <DataTable
            caption="Pipeline activity"
            columns={columns}
            data={data?.items ?? []}
            getRowId={(j) => j.id}
            total={data?.total ?? 0}
            page={data?.page ?? list.page}
            pageSize={PAGE_SIZE}
            onPageChange={list.setPage}
            noun={["job", "jobs"]}
            isLoading={jobs.isLoading}
            isFetching={jobs.isFetching}
            minWidth={1040}
            empty={<EmptyState icon={Cpu} title="No activity matches" description="Try a different stage, status or time range." />}
          />
        )}
      </Card>

      <Sheet open={!!selected} onOpenChange={(open) => (!open ? setSelected(null) : undefined)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          {selected ? (
            <>
              <SheetHeader>
                <SheetTitle className="text-lg font-bold">{JOB_KIND_LABEL[selected.kind]}</SheetTitle>
                <SheetDescription>{selected.subject}</SheetDescription>
              </SheetHeader>
              <div className="space-y-5 px-4 pb-6">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                  <div>
                    <dt className="section-label">Status</dt>
                    <dd className="mt-1">
                      <JobStatusBadge status={selected.status} />
                    </dd>
                  </div>
                  <div>
                    <dt className="section-label">Source</dt>
                    <dd className="mt-1">{selected.sourceName}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Started</dt>
                    <dd className="tnum mt-1">{formatFull(selected.startedAt)}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Duration</dt>
                    <dd className="tnum mt-1">{formatDuration(selected.durationMs)}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Retries</dt>
                    <dd className="tnum mt-1">{selected.retryCount}</dd>
                  </div>
                  <div>
                    <dt className="section-label">Job reference</dt>
                    <dd className="mt-1 font-mono text-xs break-all">{selected.id}</dd>
                  </div>
                </dl>
                {selected.errorMessage ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                    <h3 className="text-sm font-bold text-red-950">Error</h3>
                    <p className="mt-1 text-sm text-red-950">{selected.errorMessage}</p>
                  </div>
                ) : (
                  <p className="text-sm text-slate-600">No error was recorded.</p>
                )}
                <ContextNote>
                  Retrying queues another attempt. It does not mean the problem is fixed, and the result of the retry is
                  shown here once it has run.
                </ContextNote>
                <div className="flex flex-wrap gap-2">
                  {selected.retryable ? (
                    <Button size="lg" disabled={retrying === selected.id} onClick={() => retry(selected)}>
                      <RotateCw aria-hidden /> Retry
                    </Button>
                  ) : null}
                  {selected.sourceItemId ? (
                    <Button asChild variant="outline" size="lg">
                      <Link href={`/news/${selected.sourceItemId}`}>Open article</Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
