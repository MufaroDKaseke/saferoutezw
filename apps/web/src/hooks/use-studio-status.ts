"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { getStudio } from "@/lib/api/newsroom";
import type { StudioView } from "@/lib/newsroom/types";

/** How often the studio screen asks the server which version is current. */
export const STUDIO_POLL_MS = 10_000;
/** A check that has not answered by now counts as failed (kept below the poll interval so checks never overlap). */
export const STUDIO_TIMEOUT_MS = 8_000;
/** Two failed checks in a row, about 25 seconds without an answer, and the screen says it cannot confirm. */
export const STUDIO_FAILURES_BEFORE_UNCONFIRMED = 2;

export type StudioStatus =
  | "loading"
  | "current"
  | "newer_pending"
  | "not_approved"
  | "cannot_confirm"
  | "not_found";

export interface StudioState {
  status: StudioStatus;
  /** The last successful answer from the server. It stays on screen when checks fail, flagged as unconfirmed. */
  view: StudioView | null;
  /** The server's own clock at the last successful check: when the screen last heard from the record. */
  lastConfirmedAt: string | null;
  /** Failed checks in a row since the last success. */
  failures: number;
}

/**
 * What the screen says. It comes only from the last successful check against the server record: no version number
 * is ever remembered in the browser or taken from anywhere else, and once checks keep failing the answer is
 * "cannot confirm", whatever was last shown.
 */
export function deriveStudioStatus(
  view: StudioView | null,
  failures: number,
  notFound: boolean,
  threshold: number = STUDIO_FAILURES_BEFORE_UNCONFIRMED,
): StudioStatus {
  if (notFound) return "not_found";
  if (failures >= threshold) return "cannot_confirm";
  if (!view) return "loading";
  if (view.status === "not_approved") return "not_approved";
  return view.newer_revision_pending ? "newer_pending" : "current";
}

interface Options {
  pollMs?: number;
  timeoutMs?: number;
  failuresBeforeUnconfirmed?: number;
}

/**
 * Poll the studio endpoint and track the last confirmed answer.
 *
 * `setInterval` drives the checks; each one has its own `AbortController`, aborted when the screen goes away or when
 * the check times out (a timeout counts as a failure, so a hanging server cannot look like a quiet one).
 */
export function useStudioStatus(bulletinId: string, options: Options = {}): StudioState {
  const { pollMs = STUDIO_POLL_MS, timeoutMs = STUDIO_TIMEOUT_MS, failuresBeforeUnconfirmed = STUDIO_FAILURES_BEFORE_UNCONFIRMED } = options;
  const [view, setView] = useState<StudioView | null>(null);
  const [failures, setFailures] = useState(0);
  const [notFound, setNotFound] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    let stopped = false;
    let controller: AbortController | null = null;

    const check = async () => {
      if (inFlight.current) return; // the timeout settles a slow check, so checks never pile up
      inFlight.current = true;
      const current = new AbortController();
      controller = current;
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        current.abort();
      }, timeoutMs);
      try {
        const answer = await getStudio(bulletinId, current.signal);
        if (stopped) return;
        setView(answer);
        setFailures(0);
        setNotFound(false);
      } catch (error) {
        if (stopped) return;
        if (error instanceof ApiError && error.status === 404) {
          setNotFound(true);
          return;
        }
        if (error instanceof Error && error.name === "AbortError" && !timedOut) return; // aborted on purpose
        setFailures((n) => n + 1);
      } finally {
        clearTimeout(timer);
        inFlight.current = false;
      }
    };

    void check();
    const interval = setInterval(() => void check(), pollMs);
    return () => {
      stopped = true;
      clearInterval(interval);
      controller?.abort();
      inFlight.current = false;
    };
  }, [bulletinId, pollMs, timeoutMs]);

  return {
    status: deriveStudioStatus(view, failures, notFound, failuresBeforeUnconfirmed),
    view,
    lastConfirmedAt: view?.server_time ?? null,
    failures,
  };
}
