"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Loader2, Lock, MessageCircle, Smartphone } from "lucide-react";
import { AreaPicker, ChoiceCard } from "@/components/public/area-picker";
import { ErrorNotice, Notice } from "@/components/public/site-chrome";
import { Stepper } from "@/components/public/stepper";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { PROVINCES, PublicApiError, describeError, publicApi, type SubscriptionOptions } from "@/lib/public-api/client";

const FIELD =
  "h-12 w-full rounded-xl border border-input bg-white px-3.5 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

type Step = "form" | "code" | "done";

export function SubscribeForm() {
  const { t, rich } = useI18n();
  const STEPS = [t("subscribe.step.number"), t("subscribe.step.verify"), t("subscribe.step.done")];
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
  // Kept as a value and worded at render time, so it follows the language if the reader switches mid-flow.
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    publicApi.subscriptionOptions().then(setOptions).catch((e) => setError(e ?? new Error()));
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
      setError(e ?? new Error());
    } finally {
      setBusy(false);
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      if (!options) throw new PublicApiError(t("subscribe.optionsLoading"), 0, "LOADING");
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

  const channelLabel = channel === "sms" ? t("common.sms") : t("common.whatsapp");
  const errorText = error ? describeError(error, t) : null;
  const demo = options?.messaging_mode === "mock";
  const areas = allZw ? t("area.all") : [...provinces, ...corridors].join(", ");

  const card = "space-y-6 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7";

  if (step === "done") {
    return (
      <div className={card}>
        <Stepper steps={STEPS} current={2} />
        <div className="space-y-4" role="status">
          <span className="flex size-14 items-center justify-center rounded-full bg-emerald-700 text-white" aria-hidden>
            <Check className="size-7" />
          </span>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">{t("subscribe.doneTitle")}</h2>
          <p className="text-[15px] leading-relaxed text-slate-700">
            {rich("subscribe.doneBody", {
              link: (c) => (
                <Link className="font-semibold text-emerald-800 underline" href="/public/subscription/manage">
                  {c}
                </Link>
              ),
            })}
          </p>
          <dl className="divide-y divide-slate-100 rounded-xl border border-slate-200 text-sm">
            {[
              [t("subscribe.doneNumber"), `${countryCode} ${phone}`],
              [t("subscribe.doneChannel"), channelLabel],
              [t("subscribe.doneAreas"), areas || t("subscribe.areasNotSet")],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 px-4 py-3">
                <dt className="text-slate-600">{k}</dt>
                <dd className="text-right font-semibold text-slate-900">{v}</dd>
              </div>
            ))}
          </dl>
          {demo ? <Notice tone="warning">{t("common.demoMode")}</Notice> : null}
          <div className="flex flex-wrap gap-3">
            <Button asChild variant="approve" size="lg">
              <Link href="/public/subscription/manage">{t("common.manageSubscription")}</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/public/alerts">{t("common.backToAlerts")}</Link>
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
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">{t("common.enterCodeTitle")}</h2>
          <p className="text-[15px] text-slate-700">
            {rich("subscribe.sentTo", { b: (c) => <strong>{c}</strong> }, { message: notice ?? "", number: `${countryCode} ${phone}` })}
          </p>
        </div>
        {demo ? (
          <Notice tone="warning">
            {t("subscribe.demoCode")}
            {mockCode ? rich("subscribe.yourCode", { b: (c) => <strong>{c}</strong> }, { code: mockCode }) : null}
          </Notice>
        ) : null}
        <label className="grid gap-1.5 text-sm font-semibold">
          {t("common.codeLabel")}
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
            {code.length === 6 ? t("subscribe.codeReady") : t("subscribe.codeProgress", { count: code.length })}
          </span>
        </label>
        {errorText ? <ErrorNotice title={t("common.actionFailed")} message={errorText} /> : null}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" variant="approve" size="lg" className="h-12 px-6 text-base" disabled={busy || code.length !== 6}>
            {busy ? <Loader2 className="animate-spin" /> : null} {t("subscribe.verifyStart")}
          </Button>
          <Button type="button" variant="outline" size="lg" className="h-12" disabled={busy} onClick={resend}>
            {t("subscribe.resend")}
          </Button>
          <Button type="button" variant="ghost" size="lg" className="h-12" disabled={busy} onClick={() => setStep("form")}>
            {t("common.changeNumber")}
          </Button>
        </div>
      </form>
    );
  }

  const blockers = [
    !options ? t("subscribe.blocker.loading") : null,
    phone.trim().length < 5 ? t("subscribe.blocker.phone") : null,
    !allZw && provinces.length === 0 && corridors.length === 0 ? t("subscribe.blocker.area") : null,
    !consent ? t("subscribe.blocker.consent") : null,
  ].filter(Boolean) as string[];

  return (
    <form onSubmit={submit} className={card}>
      <Stepper steps={STEPS} current={0} />

      <div className="grid grid-cols-[7.5rem_1fr] gap-3">
        <label className="grid gap-1.5 text-sm font-semibold">
          {t("common.country")}
          <select className={FIELD} value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
            <option value="+263">+263 ZW</option>
            <option value="+27">+27 ZA</option>
            <option value="+260">+260 ZM</option>
            <option value="+258">+258 MZ</option>
            <option value="+267">+267 BW</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-semibold">
          {t("common.phoneNumber")}
          <input type="tel" inputMode="tel" autoComplete="tel-national" required minLength={5} maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} className={FIELD} placeholder={t("common.phonePlaceholder")} />
        </label>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-semibold">{t("subscribe.receiveBy")}</legend>
        <div className="flex flex-col gap-3 sm:flex-row">
          {(options?.channels ?? ["sms", "whatsapp"]).map((c) => (
            <ChoiceCard
              key={c}
              name="channel"
              checked={channel === c}
              onChange={() => setChannel(c)}
              title={c === "sms" ? t("common.sms") : t("common.whatsapp")}
              hint={c === "sms" ? t("subscribe.smsHint") : t("subscribe.whatsappHint")}
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

      {demo ? <Notice tone="warning">{t("common.demoMode")}</Notice> : null}
      {errorText ? <ErrorNotice title={t("common.actionFailed")} message={errorText} /> : null}

      <div className="space-y-2">
        <Button type="submit" variant="approve" size="lg" className="h-13 w-full text-base" disabled={busy || blockers.length > 0} aria-describedby="sub-blockers">
          {busy ? <Loader2 className="animate-spin" /> : <Lock />} {t("subscribe.sendCode")}
        </Button>
        <p id="sub-blockers" className="text-center text-[13px] text-slate-600">
          {blockers.length ? blockers[0] : t("subscribe.willSend", { channel: channelLabel, number: `${countryCode} ${phone}` })}
        </p>
      </div>
    </form>
  );
}
