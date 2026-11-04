"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { BrandMark, Wordmark } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SimulationNote, ContextNote } from "@/components/shared/notes";
import { useDemoSession } from "@/hooks/use-demo-session";
import { getDataMode } from "@/lib/api/config";
import { login } from "@/lib/api/auth";
import { EndpointNotAvailableError, errorMessage } from "@/lib/api/errors";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateLogin(email: string, password: string): { email?: string; password?: string } {
  const errors: { email?: string; password?: string } = {};
  if (!email.trim()) errors.email = "Enter your email address.";
  else if (!EMAIL.test(email.trim())) errors.email = "Enter a full email address, such as name@example.com.";
  if (!password) errors.password = "Enter your password.";
  return errors;
}

export function LoginForm() {
  const router = useRouter();
  const { signIn } = useDemoSession();
  const mock = getDataMode() === "mock";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    const found = validateLogin(email, password);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setPending(true);
    try {
      await login({ email: email.trim(), password });
      signIn();
      router.push("/dashboard");
    } catch (error) {
      setFormError(
        error instanceof EndpointNotAvailableError
          ? "Sign-in is not available yet because the SafeRouteZW API has no authentication endpoint."
          : errorMessage(error),
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden flex-col justify-between bg-slate-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <BrandMark className="size-11" />
          <Wordmark className="text-xl" />
        </div>
        <div className="max-w-lg">
          <h2 className="text-balance text-4xl leading-tight font-bold tracking-tight">
            Geospatial intelligence, AI-assisted evidence, human editorial control.
          </h2>
          <p className="mt-5 max-w-md text-base leading-relaxed text-slate-300">
            SafeRouteZW turns road reports into safety intelligence. The AI suggests. A named editor decides what, if
            anything, the public sees.
          </p>
        </div>
        <p className="text-sm text-slate-400">Road safety intelligence for Zimbabwe</p>
      </aside>

      <main className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-md space-y-7">
          <div className="flex items-center gap-3 lg:hidden">
            <BrandMark />
            <Wordmark tone="dark" />
          </div>
          <div>
            <h1 className="text-[1.875rem] leading-tight font-bold tracking-tight">Sign in</h1>
            <p className="mt-1.5 text-sm text-slate-600">Editors and analysts sign in to review evidence and manage alerts.</p>
          </div>

          {mock ? (
            <SimulationNote>
              <strong>Demo session.</strong> There is no real authentication yet. Any well-formed email and password
              opens the demo as a sample editor. No credentials are checked or stored.
            </SimulationNote>
          ) : (
            <ContextNote>
              Sign-in is not available yet. The backend has no authentication endpoint, so this form cannot be used.
            </ContextNote>
          )}

          <form onSubmit={submit} className="space-y-5" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-error" : undefined}
                disabled={pending || !mock}
              />
              {errors.email ? (
                <p id="email-error" role="alert" className="text-xs font-medium text-red-700">
                  {errors.email}
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
                disabled={pending || !mock}
              />
              {errors.password ? (
                <p id="password-error" role="alert" className="text-xs font-medium text-red-700">
                  {errors.password}
                </p>
              ) : null}
            </div>

            {formError ? (
              <p role="alert" className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-950">
                {formError}
              </p>
            ) : null}

            <Button type="submit" size="lg" className="w-full" disabled={pending || !mock}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {pending ? "Signing in…" : mock ? "Sign in to the demo" : "Sign in"}
            </Button>
          </form>

          {!mock ? (
            <p className="text-sm text-slate-600">
              You can still{" "}
              <Link href="/dashboard" className="font-semibold text-emerald-800 hover:underline">
                browse the dashboard
              </Link>
              . Pages show only what the API provides.
            </p>
          ) : null}
        </div>
      </main>
    </div>
  );
}
