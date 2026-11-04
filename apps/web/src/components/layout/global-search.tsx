"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, Loader2, Newspaper, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useResource } from "@/hooks/use-resource";
import { listIncidents } from "@/lib/api/incidents";
import { listNews } from "@/lib/api/news";
import { QueryError } from "@/components/shared/states";
import { INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import { formatShort } from "@/lib/formatters/date";

/**
 * Header search. It queries incidents and articles through the same API layer as
 * every page, so in api mode it reports "not available yet" rather than inventing hits.
 */
export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const debounced = useDebouncedValue(term.trim(), 250);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useResource(`search:${open ? debounced : ""}`, async () => {
    if (!open || debounced.length < 2) return null;
    const [incidents, news] = await Promise.all([
      listIncidents({ search: debounced, pageSize: 5 }),
      listNews({ search: debounced, pageSize: 5 }),
    ]);
    return { incidents, news };
  });

  const close = () => {
    setOpen(false);
    setTerm("");
  };

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        className="h-10 w-full max-w-md justify-start gap-2 font-normal text-slate-500 md:w-72 xl:w-80"
        aria-label="Search incidents, articles, roads or places"
      >
        <Search className="size-4" aria-hidden />
        <span className="truncate">Search incidents or roads</span>
        <kbd className="ml-auto hidden rounded border bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 md:inline">
          Ctrl K
        </kbd>
      </Button>

      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <DialogContent className="top-[20%] translate-y-0 gap-4 sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Search</DialogTitle>
            <DialogDescription>Find incidents and news articles by reference, headline, road or place.</DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="e.g. Rusape, collision, SR-0412"
            aria-label="Search term"
          />
          <div className="max-h-80 min-h-16 overflow-y-auto" aria-live="polite">
            {term.trim().length < 2 ? (
              <p className="text-sm text-slate-600">Type at least two characters.</p>
            ) : results.error ? (
              <QueryError error={results.error} onRetry={results.refetch} />
            ) : results.isFetching || !results.data ? (
              <p className="flex items-center gap-2 text-sm text-slate-600">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Searching…
              </p>
            ) : results.data.incidents.total + results.data.news.total === 0 ? (
              <p className="text-sm text-slate-600">Nothing matches “{debounced}”. Try a road name or a reference.</p>
            ) : (
              <div className="space-y-4">
                {results.data.incidents.items.length > 0 ? (
                  <section aria-label="Incidents">
                    <h3 className="section-label mb-1.5">Incidents</h3>
                    <ul>
                      {results.data.incidents.items.map((i) => (
                        <li key={i.id}>
                          <Link
                            href={`/incidents/${i.id}`}
                            onClick={close}
                            className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-slate-50"
                          >
                            <Activity className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
                            <span className="min-w-0">
                              <span className="block text-sm font-semibold">
                                {i.referenceCode} · {i.title}
                              </span>
                              <span className="block truncate text-xs text-slate-600">
                                {INCIDENT_TYPE_LABEL[i.incidentType]} · {i.locationText ?? "Location not stated"}
                              </span>
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {results.data.news.items.length > 0 ? (
                  <section aria-label="News articles">
                    <h3 className="section-label mb-1.5">News articles</h3>
                    <ul>
                      {results.data.news.items.map((n) => (
                        <li key={n.id}>
                          <Link
                            href={`/news/${n.id}`}
                            onClick={close}
                            className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-slate-50"
                          >
                            <Newspaper className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
                            <span className="min-w-0">
                              <span className="block text-sm font-semibold">{n.titleRedacted}</span>
                              <span className="block truncate text-xs text-slate-600">
                                {n.publisherName} · {formatShort(n.receivedAt)}
                              </span>
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
