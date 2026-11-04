import { describe, expect, it } from "vitest";
import {
  confidenceBand,
  credibilityLevel,
  deriveAlertState,
  deriveReviewState,
  deriveVerification,
  deriveWorkflowState,
  riskLevelFromScore,
  scoreSegments,
} from "./derive";

describe("scores", () => {
  it("bands geographic risk, and treats a missing score as not assessed", () => {
    expect(riskLevelFromScore(null)).toBeNull();
    expect(riskLevelFromScore(0.2)).toBe("low");
    expect(riskLevelFromScore(0.5)).toBe("medium");
    expect(riskLevelFromScore(0.8)).toBe("high");
    expect(riskLevelFromScore(0.95)).toBe("critical");
  });

  it("keeps credibility and extraction confidence on their own scales", () => {
    expect(credibilityLevel(0.58)).toBe("moderate");
    expect(credibilityLevel(0.2)).toBe("low");
    expect(confidenceBand(0.82)).toBe("high");
    expect(confidenceBand(0.58)).toBe("low");
  });

  it("fills 1 to 5 meter segments", () => {
    expect(scoreSegments(null)).toBe(0);
    expect(scoreSegments(0.58)).toBe(2);
    expect(scoreSegments(0.8)).toBe(4);
    expect(scoreSegments(1)).toBe(5);
    expect(scoreSegments(0.01)).toBe(1);
  });
});

describe("review state: only a human decision moves an incident out of pending", () => {
  it("stays pending for candidates and under-review incidents with no decision", () => {
    expect(deriveReviewState("candidate", [])).toBe("pending");
    expect(deriveReviewState("under_review", [])).toBe("pending");
  });

  it("reports needs_changes only when the latest decision says so", () => {
    expect(
      deriveReviewState("under_review", [{ decision: "needs_changes", reviewedAt: "2026-11-02T08:00:00Z" }]),
    ).toBe("needs_changes");
    expect(
      deriveReviewState("under_review", [
        { decision: "needs_changes", reviewedAt: "2026-11-02T08:00:00Z" },
        { decision: "needs_changes", reviewedAt: "2026-11-02T09:00:00Z" },
      ]),
    ).toBe("needs_changes");
  });

  it("maps final statuses", () => {
    expect(deriveReviewState("approved", [])).toBe("approved");
    expect(deriveReviewState("published", [])).toBe("approved");
    expect(deriveReviewState("rejected", [])).toBe("rejected");
  });
});

describe("verification: relevance and AI are never verification", () => {
  it("counts only supporting evidence toward corroboration", () => {
    expect(deriveVerification("candidate", [{ role: "primary" }])).toBe("single_source");
    expect(deriveVerification("candidate", [{ role: "primary" }, { role: "corroborating" }])).toBe("corroborated");
    expect(deriveVerification("candidate", [{ role: "primary" }, { role: "context" }])).toBe("single_source");
    expect(deriveVerification("candidate", [])).toBe("unverified");
  });

  it("only an editor decision makes wording editor-approved", () => {
    expect(deriveVerification("approved", [{ role: "primary" }])).toBe("editor_confirmed");
    expect(deriveVerification("rejected", [{ role: "primary" }, { role: "corroborating" }])).toBe("unverified");
  });
});

describe("alert state: approval is not distribution", () => {
  it("an approved bulletin with no channel entries has not been sent", () => {
    expect(deriveAlertState("ready", [])).toBe("approved_not_published");
  });

  it("a published alert with a failed channel is delivery_failed, not published", () => {
    expect(deriveAlertState("published", [{ status: "sent" }, { status: "failed" }])).toBe("delivery_failed");
  });

  it("is published only when no channel is failed or pending", () => {
    expect(deriveAlertState("published", [{ status: "sent" }, { status: "sent" }])).toBe("published");
    expect(deriveAlertState("published", [{ status: "sent" }, { status: "pending" }])).toBe("publication_pending");
    expect(deriveAlertState("ready", [{ status: "sending" }])).toBe("publication_pending");
  });

  it("withdrawn wins", () => {
    expect(deriveAlertState("withdrawn", [{ status: "failed" }])).toBe("withdrawn");
  });
});

describe("article workflow", () => {
  const relevant = { decision: "relevant" as const };
  it("is new until screened", () => {
    expect(deriveWorkflowState({ screening: null, retrieval: "pending", extraction: "not_started" })).toBe("new");
  });
  it("filters out irrelevant articles", () => {
    expect(
      deriveWorkflowState({ screening: { decision: "not_relevant" }, retrieval: "skipped", extraction: "not_started" }),
    ).toBe("filtered");
  });
  it("walks relevant articles through retrieval and extraction", () => {
    expect(deriveWorkflowState({ screening: relevant, retrieval: "pending", extraction: "not_started" })).toBe("awaiting_full_text");
    expect(deriveWorkflowState({ screening: relevant, retrieval: "retrieved", extraction: "not_started" })).toBe("full_text_retrieved");
    expect(deriveWorkflowState({ screening: relevant, retrieval: "retrieved", extraction: "pending" })).toBe("extraction_pending");
    expect(deriveWorkflowState({ screening: relevant, retrieval: "retrieved", extraction: "succeeded" })).toBe("processed");
  });
  it("reports failures at either stage", () => {
    expect(deriveWorkflowState({ screening: relevant, retrieval: "failed", extraction: "not_started" })).toBe("failed");
    expect(deriveWorkflowState({ screening: relevant, retrieval: "retrieved", extraction: "failed" })).toBe("failed");
  });
});
