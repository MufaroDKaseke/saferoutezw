"use client";

import Link from "next/link";
import { useState } from "react";
import { Archive, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/shared/page-header";
import { FilterBar, FilterField, SearchField, SelectField } from "@/components/shared/filters";
import { CardBodySkeleton, EmptyState, QueryError, TableSkeleton } from "@/components/shared/states";
import { Chip } from "@/components/shared/status";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useResource, type Resource } from "@/hooks/use-resource";
import { errorMessage } from "@/lib/api/errors";
import { getArchivedBulletin, searchArchive, searchArchivedBulletins } from "@/lib/api/newsroom";
import { formatFull } from "@/lib/formatters/date";
import { formatClock } from "@/lib/newsroom/reading-time";
import { NEWS_CATEGORY_OPTIONS } from "@/lib/newsroom/taxonomy";
import type { ArchiveBulletin, ArchivePage, ArchiveQuery, ArchiveStory } from "@/lib/newsroom/types";

const PAGE_SIZE = 15;

/** A `date` input value (a day, no zone) as the start of that day in the browser's clock, as an instant. */
export function dayStartIso(day: string): string | undefined {
  const date = new Date(`${day}T00:00:00`);
  return day && !Number.isNaN(date.getTime()) ? date.toISOString() : undefined;
}

/** ... and as the last moment of that day, so "to 12 Nov" includes everything aired on the 12th. */
export function dayEndIso(day: string): string | undefined {
  const date = new Date(`${day}T23:59:59.999`);
  return day && !Number.isNaN(date.getTime()) ? date.toISOString() : undefined;
}

type Tab = "stories" | "bulletins";

function StoryRow({ s }: { s: ArchiveStory }) {
  return (
    <li className="space-y-2 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        {s.category_label ? <Chip tone="indigo">{s.category_label}</Chip> : null}
        {s.follows ? (
          <Chip tone="slate" icon={GitBranch}>
            Follow-up
          </Chip>
        ) : null}
        {s.follow_up_count > 0 ? (
          <Chip tone="slate" icon={GitBranch}>
            {s.follow_up_count} {s.follow_up_count === 1 ? "follow-up" : "follow-ups"}
          </Chip>
        ) : null}
      </div>
      <h2 className="text-[15px] leading-snug font-semibold">
        <Link href={`/archive/stories/${s.id}`} className="hover:underline">
          {s.title}
        </Link>
      </h2>
      <p className="text-xs font-medium text-slate-700">Aired as: {s.headline}</p>
      <p className="max-w-3xl text-sm text-slate-700">{s.excerpt}</p>
      <p className="tnum flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
        <span>Aired {formatFull(s.aired_at)}</span>
        <span>{s.bulletins.map((b) => b.name).join(", ")}</span>
        <span>{s.reporter.display_name}</span>
        {s.follows ? (
          <span>
            Follows{" "}
            <Link href={`/archive/stories/${s.follows.id}`} className="font-medium text-emerald-800 hover:underline">
              {s.follows.title}
            </Link>
          </span>
        ) : null}
      </p>
    </li>
  );
}

/** What exactly was read in one aired revision, loaded when it is opened. */
function AiredRunningOrder({ bulletin }: { bulletin: ArchiveBulletin }) {
  const detail = useResource(`newsroom:archive:bulletin:${bulletin.id}:${bulletin.revision_number}`, () =>
    getArchivedBulletin(bulletin.id, bulletin.revision_number),
  );
  if (detail.error) return <p className="px-4 pb-4 text-sm text-slate-600">The running order could not be loaded. {errorMessage(detail.error)}</p>;
  if (!detail.data) return <CardBodySkeleton lines={3} />;
  return (
    <ol className="space-y-3 px-4 pb-4" aria-label={`Running order of ${bulletin.name}, revision ${bulletin.revision_number}`}>
      {detail.data.items.map((i) => (
        <li key={i.position} className="rounded-lg bg-slate-50 p-3 text-sm">
          <p className="font-semibold">
            <span className="tnum mr-1 text-slate-500">{i.position}.</span>
            <Link href={`/archive/stories/${i.story_id}`} className="hover:underline">
              {i.headline}
            </Link>
            <span className="tnum ml-2 text-xs font-medium text-slate-600">
              {formatClock(i.duration_seconds)}
              {i.duration_overridden ? " · clip" : ""}
            </span>
          </p>
          {i.note ? <p className="mt-1 text-xs font-semibold text-indigo-900">Note: {i.note}</p> : null}
          <p className="mt-1 leading-relaxed whitespace-pre-line text-slate-800">{i.body}</p>
        </li>
      ))}
    </ol>
  );
}

function BulletinRow({ b }: { b: ArchiveBulletin }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            {b.name} <span className="text-xs font-medium text-slate-600">· revision {b.revision_number}</span>
          </p>
          <p className="tnum mt-0.5 text-xs text-slate-600">
            Aired {formatFull(b.aired_at)} · {b.story_count} {b.story_count === 1 ? "story" : "stories"} · {formatClock(b.total_seconds)} · by{" "}
            {b.aired_by.display_name}
          </p>
        </div>
        <Button variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide running order" : "Show running order"}
        </Button>
      </div>
      {open ? <AiredRunningOrder bulletin={b} /> : null}
    </li>
  );
}

interface ResultsProps<T> {
  resource: Resource<ArchivePage<T>>;
  page: number;
  setPage: (page: number) => void;
  /** "stories" / "aired revisions": what the count counts. */
  noun: string;
  label: string;
  emptyTitle: string;
  row: (item: T) => React.ReactNode;
}

function Results<T>({ resource, page, setPage, noun, label, emptyTitle, row }: ResultsProps<T>) {
  const data = resource.data;
  if (resource.error) return <QueryError error={resource.error} onRetry={resource.refetch} what="the archive" />;
  if (!data) return <TableSkeleton rows={5} cols={3} />;
  if (data.items.length === 0) {
    return (
      <EmptyState
        icon={Archive}
        title={emptyTitle}
        description="Stories and bulletins appear here once a bulletin has been marked as broadcast. Try clearing the filters."
      />
    );
  }
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  return (
    <>
      <ul className="divide-y divide-slate-100 rounded-xl bg-card ring-1 ring-foreground/10" aria-label={label}>
        {data.items.map(row)}
      </ul>
      <nav className="flex items-center justify-between text-sm text-slate-600" aria-label="Pagination">
        <span className="tnum">
          {data.total.toLocaleString()} {noun} · page {data.page} of {pages}
        </span>
        <span className="flex gap-2">
          <Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </span>
      </nav>
    </>
  );
}

// One results component per tab, each with its own typed request. They are never swapped in place (the page gives
// each a `key`), so a tab can never be drawn from the other tab's data while its own is still loading.
function StoryResults({ query, page, setPage }: { query: ArchiveQuery; page: number; setPage: (page: number) => void }) {
  const resource = useResource(`newsroom:archive:stories:${JSON.stringify(query)}`, () => searchArchive(query));
  return (
    <Results
      resource={resource}
      page={page}
      setPage={setPage}
      noun="stories"
      label="Aired stories"
      emptyTitle="No aired stories match"
      row={(s: ArchiveStory) => <StoryRow key={s.id} s={s} />}
    />
  );
}

function BulletinResults({ query, page, setPage }: { query: ArchiveQuery; page: number; setPage: (page: number) => void }) {
  const resource = useResource(`newsroom:archive:bulletins:${JSON.stringify(query)}`, () => searchArchivedBulletins(query));
  return (
    <Results
      resource={resource}
      page={page}
      setPage={setPage}
      noun="aired revisions"
      label="Aired bulletins"
      emptyTitle="No aired bulletins match"
      row={(b: ArchiveBulletin) => <BulletinRow key={`${b.id}:${b.revision_number}`} b={b} />}
    />
  );
}

/** Everything that went to air: search the scripts and the bulletins, then open a story for its history and follow-ups. */
export function ArchiveView() {
  const [tab, setTab] = useState<Tab>("stories");
  const list = useListState({ search: "", category: undefined as string | undefined, from: "", to: "" });
  const { filters, page, setPage } = list;
  const search = useDebouncedValue(filters.search);

  const query: ArchiveQuery = {
    page,
    pageSize: PAGE_SIZE,
    q: search || undefined,
    category: tab === "stories" ? filters.category : undefined,
    airedFrom: filters.from ? dayStartIso(filters.from) : undefined,
    airedTo: filters.to ? dayEndIso(filters.to) : undefined,
  };

  const choose = (next: Tab) => {
    setTab(next);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Archive"
        description="Everything that has gone to air: the script version that was read, where and when, who approved it, and its follow-ups. Drafts that never aired are not here."
      />

      <div className="flex flex-wrap gap-2" role="group" aria-label="What to search">
        <Button variant={tab === "stories" ? "default" : "outline"} aria-pressed={tab === "stories"} onClick={() => choose("stories")}>
          Stories
        </Button>
        <Button variant={tab === "bulletins" ? "default" : "outline"} aria-pressed={tab === "bulletins"} onClick={() => choose("bulletins")}>
          Bulletins
        </Button>
      </div>

      <FilterBar onClear={list.reset} canClear={list.dirty}>
        <SearchField
          label={tab === "stories" ? "Search titles and scripts" : "Search bulletins and their stories"}
          value={filters.search}
          onChange={(v) => list.setFilter("search", v)}
          placeholder="e.g. budget, water, NUST"
        />
        {tab === "stories" ? (
          <SelectField
            label="Category"
            value={filters.category}
            onChange={(v) => list.setFilter("category", v)}
            options={NEWS_CATEGORY_OPTIONS}
            allLabel="All categories"
          />
        ) : null}
        <FilterField label="Aired from" htmlFor="archive-from">
          <Input id="archive-from" type="date" value={filters.from} onChange={(e) => list.setFilter("from", e.target.value)} />
        </FilterField>
        <FilterField label="Aired to" htmlFor="archive-to">
          <Input id="archive-to" type="date" value={filters.to} onChange={(e) => list.setFilter("to", e.target.value)} />
        </FilterField>
      </FilterBar>

      {tab === "stories" ? (
        <StoryResults key="stories" query={query} page={page} setPage={setPage} />
      ) : (
        <BulletinResults key="bulletins" query={query} page={page} setPage={setPage} />
      )}
    </div>
  );
}
