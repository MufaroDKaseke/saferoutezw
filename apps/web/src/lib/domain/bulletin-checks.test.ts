import { describe, expect, it } from "vitest";
import { checkBulletin, hasBlockingCheck } from "./bulletin-checks";

const headline = "Vehicle blocking a lane on the A5 near Gweru";

describe("checkBulletin", () => {
  it("blocks approval when the text contains a phone number", () => {
    const checks = checkBulletin(headline, "Call +263 77 123 4567 for details.", "official");
    expect(hasBlockingCheck(checks)).toBe(true);
    expect(checks.find((c) => c.id === "personal_details")?.level).toBe("block");
  });

  it("blocks approval when the text contains an email address", () => {
    expect(hasBlockingCheck(checkBulletin(headline, "Send photos to someone@example.com.", "official"))).toBe(true);
  });

  it("warns, but does not block, on casualty claims", () => {
    const checks = checkBulletin(headline, "Two people were killed, according to a report.", "official");
    expect(hasBlockingCheck(checks)).toBe(false);
    expect(checks.find((c) => c.id === "casualty_claims")?.level).toBe("warning");
  });

  it("passes clean, hedged wording once the location is confirmed", () => {
    const checks = checkBulletin(headline, "A vehicle is reported to be blocking one lane. Drive carefully.", "second_source");
    expect(checks.every((c) => c.level === "checked")).toBe(true);
  });

  it("warns that an unconfirmed location is unconfirmed", () => {
    const checks = checkBulletin(headline, "A vehicle is reported to be blocking one lane.", "unconfirmed");
    expect(checks.some((c) => c.id === "location" && c.level === "warning")).toBe(true);
  });

  it("asks for hedged wording when the location is unconfirmed and nothing says so", () => {
    const checks = checkBulletin(headline, "A vehicle is blocking one lane. Drive carefully.", "unconfirmed");
    expect(checks.some((c) => c.id === "certainty")).toBe(true);
  });
});
