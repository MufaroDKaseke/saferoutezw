"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { fetchSession, logout } from "@/lib/api/auth";
import { onUnauthenticated } from "@/lib/api/client";
import { isMockMode } from "@/lib/api/config";
import { DEMO_USER } from "@/lib/mock/data/people-sources";
import type { SessionUser } from "@/types";

/**
 * Who is signed in.
 *
 * Mock mode: a labelled demo user. "Sign out" is only remembered in this browser
 * and is NOT security.
 * API mode: a real server-side session. The browser holds only an HTTP-only
 * cookie; this hook asks the API who the session belongs to (GET /auth/me).
 * Hiding a button is never access control: FastAPI enforces every role.
 */
const KEY = "szw.demo.signed-out";
const EVENT = "szw:demo-session";

type ApiSession = { status: "loading" | "authenticated" | "anonymous"; user: SessionUser | null };
let apiSession: ApiSession = { status: "loading", user: null };
const listeners = new Set<() => void>();
let started = false;

function setApiSession(next: ApiSession) {
  apiSession = next;
  listeners.forEach((listener) => listener());
}

function startApiSession() {
  if (started) return;
  started = true;
  onUnauthenticated(() => setApiSession({ status: "anonymous", user: null }));
  fetchSession()
    .then((user) => setApiSession(user ? { status: "authenticated", user } : { status: "anonymous", user: null }))
    .catch(() => {
      // The API is unreachable: do not pretend to know. Treat as signed out so /login explains.
      setApiSession({ status: "anonymous", user: null });
    });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  window.addEventListener(EVENT, listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
    window.removeEventListener(EVENT, listener);
  };
}

const readDemoSignedOut = () => window.localStorage.getItem(KEY) === "1";
const getApiSession = () => apiSession;
const serverSession: ApiSession = { status: "loading", user: null };

export interface Session {
  /** The signed-in user, or null (signed out, or the API session is still loading). */
  user: SessionUser | null;
  /** True once we know nobody is signed in. Never true while the API session is loading. */
  signedOut: boolean;
  loading: boolean;
  /** Record a successful sign-in. In API mode pass the user returned by `login`. */
  signIn: (user?: SessionUser) => void;
  signOut: () => void | Promise<void>;
}

export function useSession(): Session {
  const demoSignedOut = useSyncExternalStore(subscribe, readDemoSignedOut, () => false);
  const api = useSyncExternalStore(subscribe, getApiSession, () => serverSession);
  const mock = isMockMode();

  useEffect(() => {
    if (!mock) startApiSession();
  }, [mock]);

  const setDemo = useCallback((value: boolean) => {
    if (value) window.localStorage.setItem(KEY, "1");
    else window.localStorage.removeItem(KEY);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  const signIn = useCallback(
    (user?: SessionUser) => {
      if (mock) setDemo(false);
      else if (user) setApiSession({ status: "authenticated", user });
    },
    [mock, setDemo],
  );

  const signOut = useCallback(async () => {
    if (mock) return setDemo(true);
    try {
      await logout();
    } finally {
      setApiSession({ status: "anonymous", user: null });
    }
  }, [mock, setDemo]);

  if (mock) {
    return { user: DEMO_USER, signedOut: demoSignedOut, loading: false, signIn, signOut };
  }
  return {
    user: api.user,
    signedOut: api.status === "anonymous",
    loading: api.status === "loading",
    signIn,
    signOut,
  };
}

/** Kept so existing components keep working; prefer `useSession`. */
export const useDemoSession = useSession;
