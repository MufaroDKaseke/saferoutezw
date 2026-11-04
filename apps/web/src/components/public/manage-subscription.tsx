"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PROVINCES, PublicApiError, publicApi, type SubscriptionOptions, type SubscriptionPreferences } from "@/lib/public-api/client";

type Step = "phone" | "code" | "manage" | "cancelled";

/** The management token lives only in component memory: closing the tab ends the session. */
export function ManageSubscription() {
  const [step, setStep] = useState<Step>("phone");
  const [countryCode, setCountryCode] = useState("+263");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [token, setToken] = useState("");
  const [prefs, setPrefs] = useState<SubscriptionPreferences | null>(null);
  const [options, setOptions] = useState<SubscriptionOptions | null>(null);
  const [mockCode, setMockCode] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  const requestCode = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const [ack, opts] = await Promise.all([
        publicApi.resendVerification({ phone, country_code: countryCode }),
        publicApi.subscriptionOptions(),
      ]);
      setOptions(opts);
      setMockCode(ack.mock_code ?? null);
      setMessage(ack.message);
      setStep("code");
    });
  };

  const verify = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const result = await publicApi.verify({ phone, country_code: countryCode, code });
      setToken(result.management_token);
      setPrefs(await publicApi.preferences(result.management_token));
      setStep("manage");
    });
  };

  const toggle = (key: "provinces" | "corridors", value: string) =>
    setPrefs((p) => (p ? { ...p, [key]: p[key].includes(value) ? p[key].filter((v) => v !== value) : [...p[key], value] } : p));

  const save = () =>
    void run(async () => {
      if (!prefs) return;
      setPrefs(await publicApi.updatePreferences(token, { all_zimbabwe: prefs.all_zimbabwe, provinces: prefs.provinces, corridors: prefs.corridors }));
      setMessage("Your preferences were saved.");
    });

  const cancel = () =>
    void run(async () => {
      await publicApi.unsubscribe(token);
      setToken("");
      setStep("cancelled");
    });

  if (step === "cancelled") {
    return <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">You have been unsubscribed. You will not receive any more alerts.</p>;
  }

  if (step === "phone") {
    return (
      <form onSubmit={requestCode} className="grid max-w-md gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-700">We send a code to your number to confirm it is yours. We never show whether a number is registered.</p>
        <div className="grid grid-cols-[7rem_1fr] gap-3">
          <label className="grid gap-1 text-sm font-medium">
            Country
            <select className="h-11 rounded-lg border border-input bg-white px-3 text-sm" value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
              <option value="+263">+263 ZW</option><option value="+27">+27 ZA</option><option value="+260">+260 ZM</option>
              <option value="+258">+258 MZ</option><option value="+267">+267 BW</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Phone number
            <Input type="tel" inputMode="tel" required minLength={5} maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} className="h-11" />
          </label>
        </div>
        {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
        <Button type="submit" size="lg" disabled={busy}>Send code</Button>
      </form>
    );
  }

  if (step === "code") {
    return (
      <form onSubmit={verify} className="grid max-w-md gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-700">{message}</p>
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
        <Button type="submit" size="lg" disabled={busy || code.length !== 6}>Continue</Button>
      </form>
    );
  }

  return (
    <div className="grid max-w-xl gap-5 rounded-xl border border-slate-200 bg-white p-4">
      {prefs ? (
        <>
          <p className="text-sm text-slate-700">Alerts are sent by <strong>{prefs.channel === "sms" ? "SMS" : "WhatsApp"}</strong>.</p>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={prefs.all_zimbabwe} onChange={(e) => setPrefs({ ...prefs, all_zimbabwe: e.target.checked })} /> All of Zimbabwe
          </label>
          {!prefs.all_zimbabwe ? (
            <fieldset className="grid gap-x-4 sm:grid-cols-2">
              <legend className="mb-1 text-sm font-medium">Provinces</legend>
              {(options?.provinces ?? [...PROVINCES]).map((p) => (
                <label key={p} className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" className="size-5" checked={prefs.provinces.includes(p)} onChange={() => toggle("provinces", p)} /> {p}
                </label>
              ))}
              {options?.corridors.map((c) => (
                <label key={c} className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" className="size-5" checked={prefs.corridors.includes(c)} onChange={() => toggle("corridors", c)} /> {c}
                </label>
              ))}
            </fieldset>
          ) : null}
          {message ? <p role="status" className="text-sm text-emerald-800">{message}</p> : null}
          {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
          <div className="flex flex-wrap gap-3">
            <Button size="lg" onClick={save} disabled={busy}>Save preferences</Button>
            <Button size="lg" variant="reject" onClick={cancel} disabled={busy}>Unsubscribe</Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
