"use client";

import { useCallback, useSyncExternalStore } from "react";
import { isMockMode } from "@/lib/api/config";
import { DEMO_USER } from "@/lib/mock/data/people-sources";
import type { DemoUser } from "@/types";

/**
 * Demo session. There is no authentication backend yet, so this is NOT security:
 * it only remembers that the visitor chose "Sign out" in this browser. Anything
 * role-sensitive must be enforced by the backend before it is trusted.
 */
const KEY = "szw.demo.signed-out";
const EVENT = "szw:demo-session";

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(EVENT, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(EVENT, listener);
  };
}

const read = () => window.localStorage.getItem(KEY) === "1";

export interface DemoSession {
  /** The demo user in mock mode. Always null in api mode: no auth backend exists. */
  user: DemoUser | null;
  signedOut: boolean;
  signIn: () => void;
  signOut: () => void;
}

export function useDemoSession(): DemoSession {
  const signedOut = useSyncExternalStore(subscribe, read, () => false);
  const set = useCallback((value: boolean) => {
    if (value) window.localStorage.setItem(KEY, "1");
    else window.localStorage.removeItem(KEY);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return {
    user: isMockMode() ? DEMO_USER : null,
    signedOut,
    signIn: () => set(false),
    signOut: () => set(true),
  };
}
