import { DEMO_USER } from "@/lib/mock/data/people-sources";
import { roleTitle } from "@/lib/newsroom/roles";
import type { SessionUser } from "@/types";
import { ApiError } from "./errors";
import { apiRequest, dual, setCsrfToken } from "./client";
import type { components } from "./schema";

type SessionOut = components["schemas"]["SessionOut"];

export interface LoginInput {
  email: string;
  password: string;
}

export interface LoginResult {
  user: SessionUser;
  /** True for the mock-mode demo session. Never a real authentication. */
  simulated: boolean;
}

function toSessionUser(out: SessionOut): SessionUser {
  setCsrfToken(out.csrf_token);
  return {
    id: out.user.id,
    name: out.user.display_name,
    email: out.user.email,
    role: out.user.role,
    // In the newsroom the editor role reads "Executive Producer" everywhere in the UI.
    title: roleTitle(out.user.role),
    isDemo: false,
  };
}

const demoUser = (): SessionUser => ({ ...DEMO_USER });

/** Mock mode opens a labelled demo session and checks nothing. API mode signs in for real. */
export function login(input: LoginInput): Promise<LoginResult> {
  return dual<LoginResult>({
    mock: () => ({ user: demoUser(), simulated: true }),
    live: async () => ({
      user: toSessionUser(await apiRequest<SessionOut>("POST /api/v1/auth/login", { body: input })),
      simulated: false,
    }),
  });
}

/** The current API session, or null when nobody is signed in. */
export async function fetchSession(): Promise<SessionUser | null> {
  try {
    return toSessionUser(await apiRequest<SessionOut>("GET /api/v1/auth/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrfToken(null);
      return null;
    }
    throw error;
  }
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<void>("POST /api/v1/auth/logout");
  } finally {
    setCsrfToken(null);
  }
}
