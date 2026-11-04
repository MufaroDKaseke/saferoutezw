"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PROVINCES, PublicApiError, publicApi, type SubscriptionOptions } from "@/lib/public-api/client";

const SELECT =
  "h-11 w-full rounded-lg border border-input bg-white px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

type Step = "form" | "code" | "done";

export function SubscribeForm() {
  const [options, setOptions] = useState<SubscriptionOptions | null>(null);
  const [step, setStep] = useState<Step>("form");
  const [countryCode, setCountryCode] = useState("+263");
  const [phone, setPhone] = useState("");
  const [channel, setChannel] = useState("sms");
  const [allZw, setAllZw] = useState(false);
  const [provinces, setProvinces] = useState<string[]>([]);
  const [corridors, setCorridors] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [mockCode, setMockCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    publicApi.subscriptionOptions().then(setOptions).catch((e) => setError(e instanceof Error ? e.message : "Could not load options."));
  }, []);

  const toggle = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof PublicApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      if (!options) throw new PublicApiError("Options are still loading.", 0, "LOADING");
      const ack = await publicApi.subscribe({
        phone, country_code: countryCode, channel, all_zimbabwe: allZw, provinces, corridors,
        consent_accepted: consent, consent_version: options.consent_version,
      });
      setMockCode(ack.mock_code ?? null);
      setNotice(ack.message);
      setStep("code");
    });
  };

  const verify = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await publicApi.verify({ phone, country_code: countryCode, code });
      setStep("done");
    });
  };

  const resend = () =>
    void run(async () => {
      const ack = await publicApi.resendVerification({ phone, country_code: countryCode });
      setMockCode(ack.mock_code ?? null);
      setNotice(ack.message);
    });

  if (step === "done") {
    return (
      <div className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4" role="status">
        <h2 className="text-lg font-semibold text-emerald-900">You are subscribed</h2>
        <p className="text-sm text-emerald-900">
          Your number is verified. You will receive reviewed SafeRouteZW alerts for the areas you chose. Reply STOP or use{" "}
          <Link className="underline" href="/public/subscription/manage">manage alerts</Link> to change or cancel.
        </p>
        {options?.messaging_mode === "mock" ? (
          <p className="text-sm font-medium text-amber-900">Demonstration mode: no real messages are sent to any phone.</p>
        ) : null}
      </div>
    );
  }

  if (step === "code") {
    return (
      <form onSubmit={verify} className="grid max-w-md gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-lg font-semibold">Enter your verification code</h2>
        <p className="text-sm text-slate-700">{notice}</p>
        {options?.messaging_mode === "mock" ? (
          <p className="rounded bg-amber-50 p-2 text-sm text-amber-900">
            Demonstration mode: no real message is sent. {mockCode ? <>Your code is <strong>{mockCode}</strong>.</> : null}
          </p>
        ) : null}
        <label className="grid gap-1 text-sm font-medium">
          6-digit code
          <Input inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="h-11 tracking-widest" />
        </label>
        {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="lg" disabled={busy || code.length !== 6}>Verify</Button>
          <Button type="button" variant="outline" size="lg" disabled={busy} onClick={resend}>Send a new code</Button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={submit} className="grid max-w-xl gap-5 rounded-xl border border-slate-200 bg-white p-4">
      <div className="grid grid-cols-[7rem_1fr] gap-3">
        <label className="grid gap-1 text-sm font-medium">
          Country
          <select className={SELECT} value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
            <option value="+263">+263 ZW</option>
            <option value="+27">+27 ZA</option>
            <option value="+260">+260 ZM</option>
            <option value="+258">+258 MZ</option>
            <option value="+267">+267 BW</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Phone number
          <Input type="tel" inputMode="tel" autoComplete="tel-national" required minLength={5} maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} className="h-11" placeholder="77 123 4567" />
        </label>
      </div>

      <fieldset className="grid gap-1">
        <legend className="mb-1 text-sm font-medium">Receive alerts by</legend>
        {(options?.channels ?? ["sms", "whatsapp"]).map((c) => (
          <label key={c} className="flex min-h-11 items-center gap-2 text-sm">
            <input type="radio" name="channel" className="size-5" checked={channel === c} onChange={() => setChannel(c)} />
            {c === "sms" ? "SMS" : "WhatsApp"}
          </label>
        ))}
      </fieldset>

      <fieldset className="grid gap-1">
        <legend className="mb-1 text-sm font-medium">Which alerts?</legend>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-5" checked={allZw} onChange={(e) => setAllZw(e.target.checked)} /> All of Zimbabwe
        </label>
        {!allZw ? (
          <div className="grid gap-x-4 sm:grid-cols-2">
            {(options?.provinces ?? [...PROVINCES]).map((p) => (
              <label key={p} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" className="size-5" checked={provinces.includes(p)} onChange={() => toggle(provinces, setProvinces, p)} /> {p}
              </label>
            ))}
          </div>
        ) : null}
        {!allZw && options?.corridors.length ? (
          <div className="mt-2">
            <p className="text-sm font-medium">Major road corridors</p>
            {options.corridors.map((c) => (
              <label key={c} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" className="size-5" checked={corridors.includes(c)} onChange={() => toggle(corridors, setCorridors, c)} /> {c}
              </label>
            ))}
          </div>
        ) : null}
      </fieldset>

      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-0.5 size-5 shrink-0" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
        <span>{(options?.consent_text ?? "").replace("{channel}", channel === "sms" ? "SMS" : "WhatsApp")}</span>
      </label>

      {options?.messaging_mode === "mock" ? (
        <p className="rounded bg-amber-50 p-2 text-sm text-amber-900">Demonstration mode: no real messages are sent to any phone.</p>
      ) : null}
      {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
      <Button type="submit" size="lg" disabled={busy || !options || !consent || (!allZw && provinces.length === 0 && corridors.length === 0)}>
        Send verification code
      </Button>
    </form>
  );
}
