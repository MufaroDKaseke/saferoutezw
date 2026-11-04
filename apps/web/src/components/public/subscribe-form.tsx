"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Loader2, Lock, MessageCircle, Smartphone } from "lucide-react";
import { AreaPicker, ChoiceCard } from "@/components/public/area-picker";
import { ErrorNotice, Notice } from "@/components/public/site-chrome";
import { Stepper } from "@/components/public/stepper";
import { Button } from "@/components/ui/button";
import { PROVINCES, PublicApiError, publicApi, type SubscriptionOptions } from "@/lib/public-api/client";

const FIELD =
  "h-12 w-full rounded-xl border border-input bg-white px-3.5 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

type Step = "form" | "code" | "done";
const STEPS = ["Your number", "Verify", "Done"];

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

  const toggle = (key: "provinces" | "corridors", value: string) => {
    const [list, set] = key === "provinces" ? [provinces, setProvinces] : [corridors, setCorridors];
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  };

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
      setCode("");
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

  const channelLabel = channel === "sms" ? "SMS" : "WhatsApp";
  const demo = options?.messaging_mode === "mock";
  const areas = allZw ? "All of Zimbabwe" : [...provinces, ...corridors].join(", ");

  const card = "space-y-6 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7";

  if (step === "done") {
    return (
      <div className={card}>
        <Stepper steps={STEPS} current={2} />
        <div className="space-y-4" role="status">
          <span className="flex size-14 items-center justify-center rounded-full bg-emerald-700 text-white" aria-hidden>
            <Check className="size-7" />
          </span>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">You are subscribed</h2>
          <p className="text-[15px] leading-relaxed text-slate-700">
            Your number is verified. You will receive reviewed SafeRouteZW alerts for the areas you chose. Reply STOP or use{" "}
            <Link className="font-semibold text-emerald-800 underline" href="/public/subscription/manage">manage alerts</Link> to change or cancel.
          </p>
          <dl className="divide-y divide-slate-100 rounded-xl border border-slate-200 text-sm">
            {[
              ["Number", `${countryCode} ${phone}`],
              ["Channel", channelLabel],
              ["Areas", areas || "Not set"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-3">
                <dt className="text-slate-600">{k}</dt>
                <dd className="text-right font-semibold text-slate-900">{v}</dd>
              </div>
            ))}
          </dl>
          {demo ? <Notice tone="warning">Demonstration mode: no real messages are sent to any phone.</Notice> : null}
          <div className="flex flex-wrap gap-3">
            <Button asChild variant="approve" size="lg">
              <Link href="/public/subscription/manage">Manage subscription</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">Back to road alerts</Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (step === "code") {
    return (
      <form onSubmit={verify} className={card}>
        <Stepper steps={STEPS} current={1} />
        <div className="space-y-2">
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">Enter the code we sent</h2>
          <p className="text-[15px] text-slate-700">
            {notice} Sent to <strong>{countryCode} {phone}</strong>.
          </p>
        </div>
        {demo ? (
          <Notice tone="warning">
            Demonstration mode: no real message is sent. {mockCode ? <>Your code is <strong>{mockCode}</strong>.</> : null}
          </Notice>
        ) : null}
        <label className="grid gap-1.5 text-sm font-semibold">
          6-digit code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{6}"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            className={`${FIELD} h-14 max-w-xs text-center text-2xl font-bold tracking-[0.5em] tnum`}
            aria-describedby="code-help"
          />
          <span id="code-help" className="text-[13px] font-normal text-slate-600">
            {code.length === 6 ? "Ready to verify." : `Enter all 6 digits (${code.length} of 6).`}
          </span>
        </label>
        {error ? <ErrorNotice title="That did not work." message={error} /> : null}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" variant="approve" size="lg" className="h-12 px-6 text-base" disabled={busy || code.length !== 6}>
            {busy ? <Loader2 className="animate-spin" /> : null} Verify and start alerts
          </Button>
          <Button type="button" variant="outline" size="lg" className="h-12" disabled={busy} onClick={resend}>
            Send a new code
          </Button>
          <Button type="button" variant="ghost" size="lg" className="h-12" disabled={busy} onClick={() => setStep("form")}>
            Change number
          </Button>
        </div>
      </form>
    );
  }

  const blockers = [
    !options ? "Loading options…" : null,
    phone.trim().length < 5 ? "Enter your phone number." : null,
    !allZw && provinces.length === 0 && corridors.length === 0 ? "Choose at least one area, or All of Zimbabwe." : null,
    !consent ? "Tick the consent box." : null,
  ].filter(Boolean) as string[];

  return (
    <form onSubmit={submit} className={card}>
      <Stepper steps={STEPS} current={0} />

      <div className="grid grid-cols-[7.5rem_1fr] gap-3">
        <label className="grid gap-1.5 text-sm font-semibold">
          Country
          <select className={FIELD} value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
            <option value="+263">+263 ZW</option>
            <option value="+27">+27 ZA</option>
            <option value="+260">+260 ZM</option>
            <option value="+258">+258 MZ</option>
            <option value="+267">+267 BW</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-semibold">
          Phone number
          <input type="tel" inputMode="tel" autoComplete="tel-national" required minLength={5} maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} className={FIELD} placeholder="77 123 4567" />
        </label>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-semibold">Receive alerts by</legend>
        <div className="flex flex-col gap-3 sm:flex-row">
          {(options?.channels ?? ["sms", "whatsapp"]).map((c) => (
            <ChoiceCard
              key={c}
              name="channel"
              checked={channel === c}
              onChange={() => setChannel(c)}
              title={c === "sms" ? "SMS" : "WhatsApp"}
              hint={c === "sms" ? "Works on any phone" : "Needs WhatsApp on this number"}
              icon={c === "sms" ? <Smartphone className="size-5" /> : <MessageCircle className="size-5" />}
            />
          ))}
        </div>
      </fieldset>

      <AreaPicker
        idPrefix="sub"
        allZimbabwe={allZw}
        onAllChange={setAllZw}
        provinces={provinces}
        corridors={corridors}
        provinceOptions={options?.provinces ?? PROVINCES}
        corridorOptions={options?.corridors ?? []}
        onToggle={toggle}
      />

      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-300 bg-white p-4 text-sm leading-relaxed has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-emerald-600/40">
        <input type="checkbox" className="mt-0.5 size-5 shrink-0 accent-emerald-700" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
        <span>{(options?.consent_text ?? "").replace("{channel}", channelLabel)}</span>
      </label>

      {demo ? <Notice tone="warning">Demonstration mode: no real messages are sent to any phone.</Notice> : null}
      {error ? <ErrorNotice title="That did not work." message={error} /> : null}

      <div className="space-y-2">
        <Button type="submit" variant="approve" size="lg" className="h-13 w-full text-base" disabled={busy || blockers.length > 0} aria-describedby="sub-blockers">
          {busy ? <Loader2 className="animate-spin" /> : <Lock />} Send verification code
        </Button>
        <p id="sub-blockers" className="text-center text-[13px] text-slate-600">
          {blockers.length ? blockers[0] : `We will send a 6-digit code by ${channelLabel} to ${countryCode} ${phone}.`}
        </p>
      </div>
    </form>
  );
}
