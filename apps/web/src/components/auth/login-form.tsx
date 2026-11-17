"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Loader2, Newspaper, NotebookPen, Radio } from "lucide-react";
import { BrandMark, NustFmLogo, Wordmark } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SimulationNote, ContextNote } from "@/components/shared/notes";
import { useDemoSession } from "@/hooks/use-demo-session";
import { getDataMode } from "@/lib/api/config";
import { login } from "@/lib/api/auth";
import { EndpointNotAvailableError, errorMessage } from "@/lib/api/errors";
import { SCOPE_NAME } from "@/lib/scope";
import { isNewsroomMode, PRODUCT_NAME } from "@/lib/app-mode";
import { cn } from "@/lib/utils";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function NewsroomWelcome() {
  return (
    <aside className="relative hidden overflow-hidden bg-brand-navy p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-16">
      <div aria-hidden className="pointer-events-none absolute -top-24 -right-64 size-[640px] rounded-full border border-brand-sky/10">
        <div className="absolute inset-16 rounded-full border border-brand-sky/10" />
        <div className="absolute inset-32 rounded-full border border-brand-sky/10" />
      </div>
      <div className="relative max-w-[420px]">
        <NustFmLogo />
        <p className="mt-5 text-xs font-medium tracking-[0.24em] text-brand-sky uppercase">The NUST FM newsroom</p>
      </div>

      <div className="relative my-14 max-w-xl">
        <div className="mb-7 h-1 w-12 rounded-full bg-brand-gold" />
        <h2 className="text-balance text-4xl leading-[1.15] font-semibold tracking-tight xl:text-5xl">
          From the first lead<br />
          <span className="text-brand-sky">to the next bulletin.</span>
        </h2>
        <p className="mt-6 max-w-md text-base leading-relaxed text-slate-300">
          Your news, your stories, your station. One space to discover what matters and prepare the stories your listeners hear.
        </p>
        <ol className="mt-10 flex gap-8 xl:gap-12" aria-label="Newsroom workflow">
          {[
            { icon: Newspaper, label: "Monitor" },
            { icon: NotebookPen, label: "Develop" },
            { icon: Radio, label: "Broadcast" },
          ].map(({ icon: Icon, label }, index) => (
            <li key={label} className="space-y-3">
              <Icon className="size-5 text-brand-sky" aria-hidden />
              <p className="text-sm font-medium"><span className="mr-2 text-xs text-slate-500">0{index + 1}</span>{label}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="relative flex items-end justify-between gap-6 border-t border-white/10 pt-6">
        <p className="max-w-64 text-xs leading-relaxed text-slate-400">
          National University of Science and Technology<br />Bulawayo, Zimbabwe
        </p>
        <p className="shrink-0 text-sm font-semibold tracking-wide text-brand-gold">101.1 FM</p>
      </div>
    </aside>
  );
}

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
      const result = await login({ email: email.trim(), password });
      signIn(result.user);
      router.push("/dashboard");
    } catch (error) {
      setFormError(
        error instanceof EndpointNotAvailableError
          ? `Sign-in is not available because the ${PRODUCT_NAME} API has no authentication endpoint.`
          : errorMessage(error),
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="grid min-h-svh lg:grid-cols-[1.05fr_1fr]">
      {isNewsroomMode ? (
        <NewsroomWelcome />
      ) : (
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
          <p className="text-sm text-slate-400">Road safety intelligence for {SCOPE_NAME}</p>
        </aside>
      )}

      <main className={cn("flex items-center justify-center bg-background px-6 py-12 sm:px-10", isNewsroomMode && "bg-white lg:border-t-4 lg:border-brand-sky")}>
        <div className="w-full max-w-md space-y-7">
          {isNewsroomMode ? (
            <div className="rounded-xl bg-brand-navy px-5 py-5 lg:hidden">
              <NustFmLogo className="mx-auto max-w-72" />
            </div>
          ) : (
            <div className="flex items-center gap-3 lg:hidden">
              <BrandMark />
              <Wordmark tone="dark" />
            </div>
          )}
          <div>
            {isNewsroomMode ? (
              <p className="mb-3 text-xs font-semibold tracking-[0.18em] text-brand-blue uppercase">Newsroom access</p>
            ) : null}
            <h1 className="text-[1.875rem] leading-tight font-bold tracking-tight">{isNewsroomMode ? "Sign in to NUST FM" : "Sign in"}</h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              {isNewsroomMode
                ? "Welcome back. Catch up on the news, develop your stories and get the next bulletin ready."
                : "Editors and analysts sign in to review evidence and manage alerts."}
            </p>
          </div>

          {mock ? (
            <SimulationNote>
              <strong>Demo session.</strong> There is no real authentication yet. Any well-formed email and password
              opens the demo as a sample editor. No credentials are checked or stored.
            </SimulationNote>
          ) : (
            <ContextNote className={isNewsroomMode ? "bg-sky-50 text-slate-700 [&>svg]:text-brand-blue" : undefined}>
              {isNewsroomMode
                ? "Use your NUST FM account. If you need access, contact your newsroom administrator."
                : "Sign in with your SafeRouteZW account. Accounts are created by an administrator; there are no shared or default logins."}
            </ContextNote>
          )}

          <form onSubmit={submit} className="space-y-5" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                className={isNewsroomMode ? "h-12 bg-white" : undefined}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-error" : undefined}
                disabled={pending}
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
                className={isNewsroomMode ? "h-12 bg-white" : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
                disabled={pending}
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

            <Button type="submit" size="lg" className={cn("w-full", isNewsroomMode && "h-12 justify-between px-4")} disabled={pending}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {pending ? "Signing in…" : mock ? "Sign in to the demo" : isNewsroomMode ? "Sign in to newsroom" : "Sign in"}
              {isNewsroomMode && !pending ? <ArrowRight className="size-4 text-brand-sky" aria-hidden /> : null}
            </Button>
          </form>

          {isNewsroomMode ? (
            <p className="border-t border-slate-100 pt-6 text-xs text-slate-500">NUST FM 101.1 <span className="mx-2 text-brand-blue" aria-hidden>·</span> Feel the vibe!</p>
          ) : null}
        </div>
      </main>
    </div>
  );
}
