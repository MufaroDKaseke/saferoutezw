"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { isMockMode } from "@/lib/api/config";
import { getVersion, subscribe } from "@/lib/mock/store";

export interface Resource<T> {
  /** Last successfully loaded data. Kept while a refetch is running, so tables do not flicker. */
  data: T | undefined;
  error: Error | null;
  /** True until the first response (data or error) arrives. */
  isLoading: boolean;
  /** True whenever a request for the current inputs is in flight. */
  isFetching: boolean;
  refetch: () => void;
}

interface Settled<T> {
  id: string;
  data?: T;
  error?: Error;
}

/**
 * Load data through the API layer.
 *
 * `key` must change whenever the inputs to `fetcher` change (use a serialised
 * query). In mock mode the hook also refetches whenever a simulated action
 * changes the shared demo state, so a decision made on one screen shows up on
 * the others.
 */
export function useResource<T>(key: string, fetcher: () => Promise<T>): Resource<T> {
  const storeVersion = useSyncExternalStore(subscribe, getVersion, getVersion);
  const version = isMockMode() ? storeVersion : 0;
  const [tick, setTick] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const requestId = `${key}|${version}|${tick}`;

  useEffect(() => {
    let cancelled = false;
    fetcherRef
      .current()
      .then((data) => {
        if (!cancelled) setSettled({ id: requestId, data });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSettled({ id: requestId, error: error instanceof Error ? error : new Error(String(error)) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  const current = settled?.id === requestId;
  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return {
    data: settled?.error ? undefined : settled?.data,
    error: current ? (settled?.error ?? null) : null,
    isLoading: settled === null,
    isFetching: !current,
    refetch,
  };
}
