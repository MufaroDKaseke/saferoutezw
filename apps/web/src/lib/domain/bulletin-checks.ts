/**
 * Pre-approval wording checks. They help an editor catch problems; they do not
 * replace the editor, and they never approve anything. In api mode the backend
 * must run its own checks again.
 */

export type CheckLevel = "block" | "warning" | "checked";

export interface BulletinCheck {
  id: "personal_details" | "casualty_claims" | "location" | "certainty";
  level: CheckLevel;
  text: string;
}

const PHONE = /(?:\+?\d[\d\s().-]{7,}\d)/;
const EMAIL = /[^\s@]+@[^\s@]+\.[^\s@]+/;
const CASUALTY = /\b(dead|death|deaths|died|killed|fatal(?:ly|ities)?|injur(?:ed|ies|y)|trapped|bodies|critical condition)\b/i;
const CERTAINTY = /\b(reported|reportedly|alleged|according to|has not been (?:independently )?confirmed|unconfirmed|not confirmed)\b/i;

export type LocationConfirmation = "unconfirmed" | "second_source" | "official" | "gps";

export const LOCATION_CONFIRMATION_LABEL: Record<LocationConfirmation, string> = {
  unconfirmed: "Unconfirmed (road and landmark only)",
  second_source: "Confirmed by a second source",
  official: "Confirmed by an official",
  gps: "Confirmed with a GPS point",
};

/** Whether the text can be approved at all. A `block` check must be fixed first. */
export function hasBlockingCheck(checks: BulletinCheck[]): boolean {
  return checks.some((c) => c.level === "block");
}

export function checkBulletin(headline: string, body: string, location: LocationConfirmation): BulletinCheck[] {
  const text = `${headline}\n${body}`;
  const checks: BulletinCheck[] = [];

  if (PHONE.test(text) || EMAIL.test(text)) {
    checks.push({
      id: "personal_details",
      level: "block",
      text: "The text contains what looks like a phone number or email address. Remove sender details before approving.",
    });
  } else {
    checks.push({ id: "personal_details", level: "checked", text: "No sender details found" });
  }

  if (CASUALTY.test(text)) {
    checks.push({
      id: "casualty_claims",
      level: "warning",
      text: "The text mentions injuries, deaths or people trapped. Include these only if an official or a second source confirms them.",
    });
  } else {
    checks.push({ id: "casualty_claims", level: "checked", text: "No unconfirmed casualty claims included" });
  }

  if (location === "unconfirmed") {
    checks.push({ id: "location", level: "warning", text: "Location: Unconfirmed. The position is known only by road and landmark." });
  }

  if (!CERTAINTY.test(text) && location === "unconfirmed") {
    checks.push({
      id: "certainty",
      level: "warning",
      text: "Nothing in the wording says the report is unconfirmed. Consider “has been reported” or “has not been confirmed”.",
    });
  }

  return checks;
}

/** Replace the pipeline's redaction markers with a neutral bar for display. */
export const REDACTION_PATTERN = /\[(?:name|phone number|email|address|id number)[^\]]*\]/gi;
