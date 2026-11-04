"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Detail pages know their own reference (SR-0412, A-0408) before the header
 * does. They publish it here and the header shows it as the last crumb. The
 * label is keyed by path so a stale label never leaks onto another page.
 */
interface Entry {
  path: string;
  label: string;
}

let entry: Entry | null = null;
const listeners = new Set<() => void>();

function set(next: Entry | null) {
  entry = next;
  listeners.forEach((l) => l());
}

export function useBreadcrumbLabel(path: string): string | null {
  const current = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
    () => entry,
    () => null,
  );
  return current && current.path === path ? current.label : null;
}

/** Render inside a detail page once its reference is known. */
export function BreadcrumbLabel({ path, label }: { path: string; label: string }) {
  useEffect(() => {
    set({ path, label });
    return () => set(null);
  }, [path, label]);
  return null;
}
