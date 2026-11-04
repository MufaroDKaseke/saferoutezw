import { DEMO_USER } from "@/lib/mock/data/people-sources";
import type { DemoUser } from "@/types";
import { route } from "./client";

export interface LoginInput {
  email: string;
  password: string;
}

export interface LoginResult {
  user: DemoUser;
  /** True for the mock-mode demo session. Never a real authentication. */
  simulated: boolean;
}

/**
 * The backend has no authentication endpoint yet, so in api mode this throws
 * EndpointNotAvailableError before anything is sent. In mock mode it opens an
 * explicitly labelled demo session and checks no credentials.
 */
export function login(input: LoginInput): Promise<LoginResult> {
  return route({
    endpoint: "POST /api/v1/auth/login",
    body: input,
    mock: () => ({ user: DEMO_USER, simulated: true }),
  });
}
