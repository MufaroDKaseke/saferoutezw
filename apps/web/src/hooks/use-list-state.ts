"use client";

import { useCallback, useState } from "react";
import type { SortState } from "@/components/shared/data-table";

/**
 * Filter, page and sort state for a list page. Changing any filter returns to
 * page 1, so a narrower result set never leaves you on an empty page.
 */
export function useListState<F extends object>(initial: F, defaultSort?: SortState) {
  const [baseline] = useState(initial);
  const [filters, setFilters] = useState<F>(initial);
  const [page, setPage] = useState(1);
  const [sort, setSortState] = useState<SortState | undefined>(defaultSort);

  const setFilter = useCallback(<K extends keyof F>(key: K, value: F[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }, []);

  const setSort = useCallback((next: SortState) => {
    setSortState(next);
    setPage(1);
  }, []);

  const reset = useCallback(() => {
    setFilters(baseline);
    setPage(1);
  }, [baseline]);

  const dirty = JSON.stringify(filters) !== JSON.stringify(baseline);

  return { filters, setFilter, page, setPage, sort, setSort, reset, dirty };
}
