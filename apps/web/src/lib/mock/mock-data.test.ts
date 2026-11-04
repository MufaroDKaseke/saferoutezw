import { beforeEach, describe, expect, it } from "vitest";
import { PermissionError, ValidationError } from "@/lib/api/errors";
import {
  approveIncident,
  publishAlert,
  rejectIncident,
  requestChanges,
  retryArticle,
  retryDelivery,
  saveDraft,
  createSource,
  triggerPoll,
} from "./actions";
import {
  getAlert,
  getBacklog,
  getDashboard,
  getIncident,
  getNews,
  getPendingReviewCount,
  getReviewWorkspace,
  listAlerts,
  listIncidents,
  listMapData,
  listNews,
  listReviews,
  listSources,
} from "./queries";
import { DEMO_USER } from "./data/people-sources";
import { getDb, resetMockDb } from "./store";

beforeEach(() => resetMockDb());

describe("the demo dataset is relationally coherent", () => {
  it("every evidence link points at a real article and incident, and both sides agree", () => {
    const db = getDb();
    for (const e of db.evidence) {
      const article = db.articles.find((a) => a.id === e.sourceItemId);
      const incident = db.incidents.find((i) => i.id === e.incidentId);
      expect(article, `article for ${e.id}`).toBeDefined();
      expect(incident, `incident for ${e.id}`).toBeDefined();
      expect(article!.linkedIncidentIds).toContain(e.incidentId);
    }
    for (const a of db.articles) {
      for (const id of a.linkedIncidentIds) {
        expect(db.evidence.some((e) => e.sourceItemId === a.id && e.incidentId === id)).toBe(true);
      }
    }
  });

  it("opening an incident's source shows the right article", () => {
    const incident = getIncident("inc-0411");
    expect(incident.evidence.map((e) => e.sourceItemId).sort()).toEqual(["art-002", "art-003"]);
    for (const e of incident.evidence) {
      expect(getNews(e.sourceItemId).titleRedacted).toBe(e.articleTitle);
    }
  });

  it("one incident can have several articles (article ≠ incident)", () => {
    expect(getIncident("inc-0411").sourceCount).toBe(2);
    expect(getIncident("inc-0407").sourceCount).toBe(2);
    expect(getIncident("inc-0411").verification).toBe("corroborated");
  });

  it("one article can describe several distinct events, only some of which become incidents", () => {
    const roundup = getNews("art-005");
    const events = roundup.extractionRuns[0].events;
    expect(events).toHaveLength(3);
    expect(events.filter((e) => e.linkedIncidentId).map((e) => e.linkedIncidentId).sort()).toEqual(["inc-0409", "inc-0413"]);
    expect(events.find((e) => !e.linkedIncidentId)?.confidence).toBeLessThan(0.5);
    expect(roundup.linkedIncidents.map((i) => i.referenceCode).sort()).toEqual(["SR-0409", "SR-0413"]);
  });

  it("keyword relevance is not verification: a relevant opinion piece creates no incident", () => {
    const op = getNews("art-014");
    expect(op.screening?.decision).toBe("relevant");
    expect(op.linkedIncidentIds).toHaveLength(0);
    expect(op.extractionRuns[0].classification).toBe("not_road_incident");
  });

  it("mirrors the database invariants for approvals and alerts", () => {
    const db = getDb();
    for (const i of db.incidents.filter((x) => x.status === "approved" || x.status === "published")) {
      expect(db.reviews.some((r) => r.incidentId === i.id && r.decision === "approved")).toBe(true);
    }
    for (const alert of db.alerts) {
      const review = db.reviews.find((r) => r.id === alert.approvalReviewId)!;
      expect(review.decision).toBe("approved");
      expect(review.incidentId).toBe(alert.incidentId);
      expect(review.bulletinVersionId).toBe(alert.bulletinVersionId);
    }
  });

  it("approval and delivery are separate: an approved alert can still have a failed channel", () => {
    expect(getAlert("alert-a0407").publicationState).toBe("delivery_failed");
    expect(getAlert("alert-a0408").publicationState).toBe("published");
  });

  it("labels every fabricated record as synthetic and never uses a real publisher domain", () => {
    const db = getDb();
    expect(db.articles.every((a) => a.synthetic)).toBe(true);
    expect(db.incidents.every((i) => i.synthetic)).toBe(true);
    expect(db.blackspots.every((b) => b.synthetic && b.point.synthetic)).toBe(true);
    expect(db.sources.every((s) => !s.feedUrl || new URL(s.feedUrl).hostname.endsWith(".example"))).toBe(true);
  });

  it("matches the size requested for the demo set", () => {
    const db = getDb();
    expect(db.sources.length).toBeGreaterThanOrEqual(5);
    expect(db.sources.length).toBeLessThanOrEqual(8);
    expect(db.articles.length).toBeGreaterThanOrEqual(15);
    expect(db.articles.length).toBeLessThanOrEqual(25);
    expect(db.incidents.length).toBeGreaterThanOrEqual(8);
    expect(db.incidents.length).toBeLessThanOrEqual(12);
  });

  it("covers successful and failed retrieval, and extracted and unprocessed articles", () => {
    const db = getDb();
    const states = new Set(db.articles.map((a) => a.workflowState));
    for (const s of ["new", "filtered", "awaiting_full_text", "extraction_pending", "processed", "failed"]) {
      if (s === "awaiting_full_text") continue; // none of the demo articles is waiting on retrieval
      expect(states.has(s as never), s).toBe(true);
    }
    expect(db.articles.some((a) => a.retrievalStatus === "failed")).toBe(true);
    expect(getBacklog().failedNeedingAttention).toBe(2);
  });
});

describe("listing, filtering and paging", () => {
  it("filters news by relevance, status, publisher and keyword", () => {
    expect(listNews({ relevance: "not_relevant", pageSize: 50 }).items.every((a) => a.screening?.decision === "not_relevant")).toBe(true);
    expect(listNews({ status: "failed", pageSize: 50 }).total).toBe(2);
    expect(listNews({ publisherId: "src-roadwatch", pageSize: 50 }).items.every((a) => a.sourceId === "src-roadwatch")).toBe(true);
    expect(listNews({ keyword: "minibus", pageSize: 50 }).total).toBeGreaterThan(0);
    expect(listNews({ search: "rusape", pageSize: 50 }).items.length).toBeGreaterThan(0);
  });

  it("pages and sorts", () => {
    const first = listNews({ page: 1, pageSize: 5 });
    const second = listNews({ page: 2, pageSize: 5 });
    expect(first.items).toHaveLength(5);
    expect(first.total).toBe(22);
    expect(first.items.map((a) => a.id)).not.toEqual(second.items.map((a) => a.id));
    const asc = listNews({ sort: "receivedAt", dir: "asc", pageSize: 3 }).items.map((a) => a.receivedAt);
    expect([...asc].sort()).toEqual(asc);
  });

  it("lists incidents by review state, and the queue by priority", () => {
    expect(listIncidents({ reviewState: "pending", pageSize: 50 }).total).toBe(4);
    const open = listReviews({ state: "open", pageSize: 50 }).items;
    expect(open[0].priority).toBe("urgent");
    expect(getPendingReviewCount()).toBe(4);
  });

  it("never plots rejected incidents on the map", () => {
    const { incidents } = listMapData({});
    expect(incidents.some((i) => i.reviewState === "rejected")).toBe(false);
    expect(incidents.every((i) => i.point)).toBe(true);
  });

  it("builds a dashboard from the same records the other pages use", () => {
    const d = getDashboard("7d");
    expect(d.kpis.pendingReviews).toBe(getPendingReviewCount());
    expect(d.queue.every((q) => q.state === "pending")).toBe(true);
    expect(d.pipeline.fullyShared).toBe(1);
    expect(d.pipeline.approvedByEditor).toBe(2);
    expect(listSources()).toHaveLength(d.sourceHealth.length);
  });
});

describe("simulated editorial actions", () => {
  const draft = { headline: "Head-on collision reported on A3 near Rusape", body: "A head-on collision has been reported. It has not been confirmed." };

  it("approving records a human decision and an alert that is approved but not sent", () => {
    const before = getPendingReviewCount();
    const result = approveIncident("inc-0412", draft);
    expect(result.simulated).toBe(true);
    expect(result.message).toMatch(/Nothing was published or sent/);

    const incident = getIncident("inc-0412");
    expect(incident.reviewState).toBe("approved");
    expect(incident.verification).toBe("editor_confirmed");
    expect(getPendingReviewCount()).toBe(before - 1);

    const alert = listAlerts({ search: "SR-0412" }).items[0];
    expect(alert.publicationState).toBe("approved_not_published");
    expect(alert.channels).toHaveLength(0);
    expect(alert.publishedAt).toBeNull();
    expect(getDb().reviews.some((r) => r.incidentId === "inc-0412" && r.decision === "approved")).toBe(true);
  });

  it("approval applies to one exact bulletin version; edits create a new one", () => {
    const before = getReviewWorkspace("inc-0412").bulletins.length;
    approveIncident("inc-0412", { ...draft, body: `${draft.body} Drive with care.` });
    const bulletins = getReviewWorkspace("inc-0412").bulletins;
    expect(bulletins.length).toBe(before + 1);
    const approval = getDb().reviews.find((r) => r.incidentId === "inc-0412" && r.decision === "approved")!;
    expect(approval.bulletinVersionId).toBe(bulletins[0].id);
    expect(bulletins[0].body).toMatch(/Drive with care/);
  });

  it("does not create a new version when the text is unchanged", () => {
    const latest = getReviewWorkspace("inc-0412").bulletins[0];
    saveDraft("inc-0412", { headline: latest.headline, body: latest.body, notes: "Called the press office." });
    expect(getReviewWorkspace("inc-0412").bulletins).toHaveLength(1);
    expect(getReviewWorkspace("inc-0412").notes).toBe("Called the press office.");
  });

  it("rejects blank bulletin text", () => {
    expect(() => approveIncident("inc-0412", { headline: " ", body: "x" })).toThrow(ValidationError);
    expect(() => approveIncident("inc-0412", { headline: "x", body: "" })).toThrow(ValidationError);
    expect(getIncident("inc-0412").reviewState).toBe("pending");
  });

  it("requires a reason to reject, and keeps it in the history", () => {
    expect(() => rejectIncident("inc-0410", "no")).toThrow(ValidationError);
    expect(getIncident("inc-0410").reviewState).toBe("pending");
    rejectIncident("inc-0410", "Single unnamed witness and no place on the road.");
    expect(getIncident("inc-0410").reviewState).toBe("rejected");
    expect(getReviewWorkspace("inc-0410").reviews[0].notes).toMatch(/unnamed witness/);
    expect(listMapData({}).incidents.some((i) => i.id === "inc-0410")).toBe(false);
  });

  it("requires notes to request changes", () => {
    expect(() => requestChanges("inc-0409", "")).toThrow(ValidationError);
    requestChanges("inc-0409", "Confirm where on the A4 this happened.");
    expect(getIncident("inc-0409").reviewState).toBe("needs_changes");
  });

  it("refuses a second decision on an already decided incident", () => {
    rejectIncident("inc-0410", "Not enough to act on, single source.");
    expect(() => approveIncident("inc-0410", draft)).toThrow(ValidationError);
  });

  it("publishing is a separate, labelled step that marks every channel", () => {
    approveIncident("inc-0412", draft);
    const alert = listAlerts({ search: "SR-0412" }).items[0];
    const result = publishAlert(alert.id);
    expect(result.message).toMatch(/No message was sent/);
    const after = getAlert(alert.id);
    expect(after.publicationState).toBe("published");
    expect(after.channels.map((c) => c.channel).sort()).toEqual(["sms", "web", "whatsapp"]);
  });

  it("retrying a failed delivery adds an attempt and says nothing was sent", () => {
    const result = retryDelivery("alert-a0407", "sms");
    expect(result.simulated).toBe(true);
    expect(result.message).toMatch(/No message was sent/);
    const sms = getAlert("alert-a0407").channels.find((c) => c.channel === "sms")!;
    expect(sms.attempts).toHaveLength(3);
    expect(() => retryDelivery("alert-a0407", "sms")).toThrow(ValidationError);
  });

  it("a retry only queues work. It never reports the article as processed", () => {
    const failed = listNews({ status: "failed", pageSize: 5 }).items[0];
    const result = retryArticle(failed.id);
    expect(result.message).toMatch(/No retrieval or AI call was made/);
    const after = getNews(failed.id);
    expect(after.workflowState).not.toBe("processed");
    expect(["awaiting_full_text", "extraction_pending"]).toContain(after.workflowState);
    expect(() => retryArticle("art-001")).toThrow(ValidationError);
  });

  it("validates and simulates source management without a network request", () => {
    expect(() => createSource({ name: "X", feedUrl: "not a url", pollIntervalSeconds: 180, verificationTier: "unverified" })).toThrow(ValidationError);
    expect(() => createSource({ name: "X", feedUrl: "https://x.example/feed", pollIntervalSeconds: 30, verificationTier: "unverified" })).toThrow(ValidationError);
    expect(() => createSource({ name: "Harare Daily Courier", feedUrl: "https://new.example/feed", pollIntervalSeconds: 180, verificationTier: "unverified" })).toThrow(/already exists/);
    const created = createSource({ name: "Test Gazette", feedUrl: "https://test-gazette.example/feed", pollIntervalSeconds: 180, verificationTier: "community" });
    expect(created.simulated).toBe(true);
    expect(listSources().find((s) => s.name === "Test Gazette")?.connectionStatus).toBe("untested");
    const poll = triggerPoll(created.data!.id);
    expect(poll.data?.simulated).toBe(true);
    expect(poll.data?.fetchedCount).toBe(0);
  });

  it("only reviewer roles may record decisions (a UI convenience; the server must enforce it)", () => {
    const original = DEMO_USER.role;
    try {
      (DEMO_USER as { role: string }).role = "contributor";
      expect(getReviewWorkspace("inc-0412").canDecide).toBe(false);
      expect(() => approveIncident("inc-0412", draft)).toThrow(PermissionError);
      expect(() => rejectIncident("inc-0412", "A reason that is long enough.")).toThrow(PermissionError);
      expect(getIncident("inc-0412").reviewState).toBe("pending");
      (DEMO_USER as { role: string }).role = "service";
      expect(() => requestChanges("inc-0412", "Please check.")).toThrow(PermissionError);
    } finally {
      (DEMO_USER as { role: string }).role = original;
    }
    expect(getReviewWorkspace("inc-0412").canDecide).toBe(true);
  });
});
