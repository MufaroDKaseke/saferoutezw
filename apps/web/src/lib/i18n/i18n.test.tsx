import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SeverityBadge } from "@/components/public/hazard";
import { LOCALES, isLocale } from "@/lib/i18n/config";
import { MESSAGES } from "@/lib/i18n/messages";
import { en } from "@/lib/i18n/messages/en";
import { I18nProvider } from "@/lib/i18n/provider";
import { createTranslator } from "@/lib/i18n/translate";
import { PublicApiError, describeError, formatDuration } from "@/lib/public-api/client";

/** Every {placeholder} and <tag> in the English text must survive translation, or a value would silently disappear. */
const tokens = (text: string) => [...text.matchAll(/\{\w+\}|<\/?\w+>/g)].map((m) => m[0]).sort();

describe("translations", () => {
  it("offers English, ChiShona and isiNdebele", () => {
    expect([...LOCALES]).toEqual(["en", "sn", "nd"]);
    expect(isLocale("sn")).toBe(true);
    expect(isLocale("fr")).toBe(false);
  });

  it.each(["sn", "nd"] as const)("%s keeps every placeholder and tag the English text has", (locale) => {
    for (const [key, english] of Object.entries(en)) {
      const translated = (MESSAGES[locale] as Record<string, string>)[key];
      expect(tokens(translated), `${locale}: ${key}`).toEqual(tokens(english));
    }
  });

  it.each(["sn", "nd"] as const)("%s has no empty text and differs from English where it should", (locale) => {
    const table = MESSAGES[locale] as Record<string, string>;
    for (const [key, value] of Object.entries(table)) expect(value.trim().length, `${locale}: ${key}`).toBeGreaterThan(0);
    // Spot checks on the text a reader needs most: a copy-and-paste of English here would be a bug.
    for (const key of ["footer.disclaimer", "common.noAlertNotSafe", "severity.fatal.label", "home.title"]) {
      expect(table[key], `${locale}: ${key}`).not.toBe((en as Record<string, string>)[key]);
    }
  });
});

describe("translator", () => {
  const t = createTranslator("en", MESSAGES.en);

  it("fills values and picks singular or plural from count", () => {
    expect(t.t("alerts.pageOf", { page: 2, pages: 5 })).toBe("Page 2 of 5");
    expect(t.t("alerts.count", { count: 1 })).toBe("1 published notice");
    expect(t.t("alerts.count", { count: 3 })).toBe("3 published notices");
  });

  it("maps <tag> markup to elements", () => {
    render(<p>{t.rich("manage.buttonSave", { b: (c) => <strong>{c}</strong> })}</p>);
    expect(screen.getByText("Save changes").tagName).toBe("STRONG");
  });

  it("returns undefined for an unknown dynamic key so the caller can fall back", () => {
    expect(t.maybe("hazard.not_a_real_type")).toBeUndefined();
    expect(t.maybe("hazard.collision")).toBe("Collision");
  });
});

describe("components follow the chosen language", () => {
  it("shows the severity word in ChiShona and isiNdebele, and English without a provider", () => {
    const { unmount } = render(
      <I18nProvider locale="sn" messages={MESSAGES.sn}>
        <SeverityBadge severity="fatal" />
      </I18nProvider>,
    );
    expect(screen.getByText("Rufu")).toBeInTheDocument();
    unmount();

    const nd = render(
      <I18nProvider locale="nd" messages={MESSAGES.nd}>
        <SeverityBadge severity="fatal" />
      </I18nProvider>,
    );
    expect(screen.getByText("Ukufa")).toBeInTheDocument();
    nd.unmount();

    render(<SeverityBadge severity="fatal" />);
    expect(screen.getByText("Fatal")).toBeInTheDocument();
  });
});

describe("error wording and durations", () => {
  const sn = createTranslator("sn", MESSAGES.sn).t;

  it("words the app's own errors in the reader's language but leaves API messages as sent", () => {
    expect(describeError(new PublicApiError("x", 0, "NETWORK"), sn)).toBe(MESSAGES.sn["error.network"]);
    expect(describeError(new PublicApiError("x", 429, "RATE"), sn)).toBe(MESSAGES.sn["error.rateLimited"]);
    expect(describeError(new PublicApiError("That code has expired.", 400, "CODE_EXPIRED"), sn)).toBe("That code has expired.");
    expect(describeError(new Error("boom"), sn)).toBe(MESSAGES.sn["error.generic"]);
  });

  it("formats durations with translated unit words", () => {
    expect(formatDuration(65 * 60)).toBe("1 h 5 min");
    expect(formatDuration(65 * 60, sn)).toBe("1 awa 5 min");
  });
});
