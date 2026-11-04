"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { AreaPicker } from "@/components/public/area-picker";
import { ErrorNotice, Notice } from "@/components/public/site-chrome";
import { Stepper } from "@/components/public/stepper";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";
import { PROVINCES, describeError, publicApi, type SubscriptionOptions, type SubscriptionPreferences } from "@/lib/public-api/client";

const FIELD =
  "h-12 w-full rounded-xl border border-input bg-white px-3.5 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

type Step = "phone" | "code" | "manage" | "cancelled";

/** The management token lives only in component memory: closing the tab ends the session. */
export function ManageSubscription() {
  const { t, rich } = useI18n();
  const STEPS = [t("subscribe.step.number"), t("subscribe.step.verify"), t("manage.step.manage")];
  const [step, setStep] = useState<Step>("phone");
  const [countryCode, setCountryCode] = useState("+263");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [token, setToken] = useState("");
  const [prefs, setPrefs] = useState<SubscriptionPreferences | null>(null);
  const [options, setOptions] = useState<SubscriptionOptions | null>(null);
  const [mockCode, setMockCode] = useState<string | null>(null);
  // `message` is wording from the API (a code was sent) or null; `saved` marks our own "preferences saved" note.
  const [message, setMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // Kept as a value and worded at render time, so it follows the language if the reader switches mid-flow.
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);

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
      setMessage(null);
      setSaved(false);
      setStep("manage");
    });
  };

  const toggle = (key: "provinces" | "corridors", value: string) =>
    setPrefs((p) => (p ? { ...p, [key]: p[key].includes(value) ? p[key].filter((v) => v !== value) : [...p[key], value] } : p));

  const save = () =>
    void run(async () => {
      if (!prefs) return;
      setPrefs(await publicApi.updatePreferences(token, { all_zimbabwe: prefs.all_zimbabwe, provinces: prefs.provinces, corridors: prefs.corridors }));
      setSaved(true);
    });

  const cancel = () =>
    void run(async () => {
      await publicApi.unsubscribe(token);
      setToken("");
      setStep("cancelled");
    });

  const card = "space-y-6 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7";
  const demo = options?.messaging_mode === "mock";
  const errorText = error ? describeError(error, t) : null;
  const channelLabel = prefs?.channel === "sms" ? t("common.sms") : t("common.whatsapp");

  if (step === "cancelled") {
    return (
      <div className={card} role="status">
        <Stepper steps={STEPS} current={2} />
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">{t("manage.unsubscribedTitle")}</h2>
        <p className="text-[15px] text-slate-700">{t("manage.unsubscribedBody")}</p>
        <div className="flex flex-wrap gap-3">
          <Button asChild variant="outline" size="lg"><Link href="/public/alerts">{t("common.backToAlerts")}</Link></Button>
          <Button asChild variant="approve" size="lg"><Link href="/public/subscribe">{t("manage.subscribeAgain")}</Link></Button>
        </div>
      </div>
    );
  }

  if (step === "phone") {
    return (
      <form onSubmit={requestCode} className={card}>
        <Stepper steps={STEPS} current={0} />
        <p className="flex items-start gap-2 text-[15px] leading-relaxed text-slate-700">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-700" aria-hidden />
          {t("manage.prove")}
        </p>
        <div className="grid grid-cols-[7.5rem_1fr] gap-3">
          <label className="grid gap-1.5 text-sm font-semibold">
            {t("common.country")}
            <select className={FIELD} value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
              <option value="+263">+263 ZW</option><option value="+27">+27 ZA</option><option value="+260">+260 ZM</option>
              <option value="+258">+258 MZ</option><option value="+267">+267 BW</option>
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">
            {t("common.phoneNumber")}
            <input type="tel" inputMode="tel" autoComplete="tel-national" required minLength={5} maxLength={32} value={phone} onChange={(e) => setPhone(e.target.value)} className={FIELD} placeholder={t("common.phonePlaceholder")} />
          </label>
        </div>
        {errorText ? <ErrorNotice title={t("common.actionFailed")} message={errorText} /> : null}
        <Button type="submit" variant="approve" size="lg" className="h-12 w-full text-base sm:w-auto sm:px-8" disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : null} {t("manage.sendCode")}
        </Button>
      </form>
    );
  }

  if (step === "code") {
    return (
      <form onSubmit={verify} className={card}>
        <Stepper steps={STEPS} current={1} />
        <div className="space-y-2">
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">{t("common.enterCodeTitle")}</h2>
          <p className="text-[15px] text-slate-700">{message}</p>
        </div>
        {demo ? (
          <Notice tone="warning">
            {t("subscribe.demoCode")}
            {mockCode ? rich("subscribe.yourCode", { b: (c) => <strong>{c}</strong> }, { code: mockCode }) : null}
          </Notice>
        ) : null}
        <label className="grid gap-1.5 text-sm font-semibold">
          {t("common.codeLabel")}
          <input inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={`${FIELD} h-14 max-w-xs text-center text-2xl font-bold tracking-[0.5em] tnum`} />
        </label>
        {errorText ? <ErrorNotice title={t("common.actionFailed")} message={errorText} /> : null}
        <div className="flex flex-wrap gap-3">
          <Button type="submit" variant="approve" size="lg" className="h-12 px-6 text-base" disabled={busy || code.length !== 6}>
            {busy ? <Loader2 className="animate-spin" /> : null} {t("manage.continue")}
          </Button>
          <Button type="button" variant="ghost" size="lg" className="h-12" disabled={busy} onClick={() => setStep("phone")}>{t("common.changeNumber")}</Button>
        </div>
      </form>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
      <div className={card}>
        <Stepper steps={STEPS} current={2} />
        {prefs ? (
          <>
            <div className="flex items-center gap-3 rounded-xl bg-emerald-50 p-3.5 text-sm text-emerald-950">
              <Check className="size-5 shrink-0 text-emerald-700" aria-hidden />
              <p>
                {rich("manage.confirmed", { b: (c) => <strong>{c}</strong> }, { channel: channelLabel })}
              </p>
            </div>
            <h2 className="text-xl font-extrabold tracking-tight text-slate-900">{t("manage.prefsTitle")}</h2>
            <AreaPicker
              idPrefix="manage"
              allZimbabwe={prefs.all_zimbabwe}
              onAllChange={(all) => setPrefs({ ...prefs, all_zimbabwe: all })}
              provinces={prefs.provinces}
              corridors={prefs.corridors}
              provinceOptions={options?.provinces ?? PROVINCES}
              corridorOptions={options?.corridors ?? []}
              onToggle={toggle}
            />
            {saved ? (
              <Notice tone="info" role="status">
                <strong className="font-semibold">{t("manage.saved")}</strong> {t("manage.appliesNext")}
              </Notice>
            ) : null}
            {errorText ? <ErrorNotice title={t("common.actionFailed")} message={errorText} /> : null}
            <Button variant="approve" size="lg" className="h-12 px-6 text-base" onClick={save} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : null} {t("manage.save")}
            </Button>
          </>
        ) : null}
      </div>

      <aside className="space-y-4" aria-label={t("manage.unsubscribeAside")}>
        <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="font-bold text-slate-900">{t("manage.stopAll")}</h2>
          <p className="text-sm leading-relaxed text-slate-600">{t("manage.stopAllBody")}</p>
          {confirmCancel ? (
            <div className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-3" role="alertdialog" aria-label={t("manage.confirmDialog")}>
              <p className="text-sm font-semibold text-red-900">{t("manage.confirmQuestion")}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="reject" size="lg" onClick={cancel} disabled={busy}>
                  {busy ? <Loader2 className="animate-spin" /> : <Trash2 />} {t("manage.confirmYes")}
                </Button>
                <Button variant="outline" size="lg" onClick={() => setConfirmCancel(false)}>{t("manage.keep")}</Button>
              </div>
            </div>
          ) : (
            <Button variant="reject" size="lg" onClick={() => setConfirmCancel(true)}>
              <Trash2 /> {t("manage.unsubscribe")}
            </Button>
          )}
        </section>
        <section className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-700">
          <h2 className="font-bold text-slate-900">{t("manage.buttons")}</h2>
          <p>{rich("manage.buttonSave", { b: (c) => <strong>{c}</strong> })}</p>
          <p>{rich("manage.buttonUnsub", { b: (c) => <strong>{c}</strong> })}</p>
        </section>
      </aside>
    </div>
  );
}
