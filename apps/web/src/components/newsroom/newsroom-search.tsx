"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Loader2, Newspaper, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { QueryError } from "@/components/shared/states";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useResource } from "@/hooks/use-resource";
import { listNewsroomArticles } from "@/lib/api/newsroom";
import { formatShort } from "@/lib/formatters/date";
import { newsCategoryLabel } from "@/lib/newsroom/taxonomy";

/** Header search for the newsroom: articles only (headline, excerpt, text and AI summary). */
export function NewsroomSearch() {
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

  const results = useResource(`newsroom:search:${open ? debounced : ""}`, async () =>
    open && debounced.length >= 2 ? listNewsroomArticles({ q: debounced, pageSize: 8 }) : null,
  );

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
        aria-label="Search articles"
      >
        <Search className="size-4" aria-hidden />
        <span className="truncate">Search articles</span>
        <kbd className="ml-auto hidden rounded border bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 md:inline">Ctrl K</kbd>
      </Button>

      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <DialogContent className="top-[20%] translate-y-0 gap-4 sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Search articles</DialogTitle>
            <DialogDescription>Find collected articles by headline, text or AI summary.</DialogDescription>
          </DialogHeader>
          <Input autoFocus value={term} onChange={(e) => setTerm(e.target.value)} placeholder="e.g. budget, NUST, tollgate" aria-label="Search term" />
          <div className="max-h-80 min-h-16 overflow-y-auto" aria-live="polite">
            {term.trim().length < 2 ? (
              <p className="text-sm text-slate-600">Type at least two characters.</p>
            ) : results.error ? (
              <QueryError error={results.error} onRetry={results.refetch} />
            ) : results.isFetching || !results.data ? (
              <p className="flex items-center gap-2 text-sm text-slate-600">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Searching…
              </p>
            ) : results.data.total === 0 ? (
              <p className="text-sm text-slate-600">Nothing matches “{debounced}”.</p>
            ) : (
              <ul>
                {results.data.items.map((a) => (
                  <li key={a.id}>
                    <Link href={`/news/${a.id}`} onClick={close} className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-slate-50">
                      <Newspaper className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold">{a.headline}</span>
                        <span className="block truncate text-xs text-slate-600">
                          {a.publisher} · {newsCategoryLabel(a.category)} · {formatShort(a.collected_at)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
