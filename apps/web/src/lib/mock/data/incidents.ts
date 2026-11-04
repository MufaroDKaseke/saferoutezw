import type {
  ChannelKind,
  EvidenceRole,
  GeoPoint,
  IncidentStatus,
  IncidentType,
  Province,
  ReviewDecision,
  ReviewPriority,
  Severity,
} from "@/types";

/**
 * SYNTHETIC incident candidates. Positions are illustrative placements near the
 * named road or town (see `accuracy`) and are never exact crash sites.
 */

export interface IncidentSeed {
  id: string;
  ref: string;
  title: string;
  type: IncidentType;
  severity: Severity;
  locationText: string;
  roadName: string;
  province: Province;
  point: Pick<GeoPoint, "lat" | "lng" | "accuracy"> | null;
  occurredCat: string | null;
  occurredNote: string | null;
  credibility: number;
  credibilityRationale: string;
  risk: number;
  priority: ReviewPriority;
  status: IncidentStatus;
  summary: string;
  vehicles: string[];
  traffic: string | null;
  missing: string[];
  createdCat: string;
  evidence: { articleId: string; role: EvidenceRole; eventId: string }[];
  /** Time an editor first opened the incident, if any. */
  openedCat?: string;
}

export const INCIDENTS: IncidentSeed[] = [
  {
    id: "inc-0412",
    ref: "SR-0412",
    title: "Head-on collision near Rusape",
    type: "collision",
    severity: "serious",
    locationText: "A3 Harare–Mutare road, after the Headlands turn-off, near Rusape",
    roadName: "A3 Harare–Mutare road",
    province: "Manicaland",
    point: { lat: -18.512, lng: 32.098, accuracy: "approximate" },
    occurredCat: null,
    occurredNote: "Not stated. Report received 14:52.",
    credibility: 0.58,
    credibilityRationale: "One source, plausible detail, no corroboration yet.",
    risk: 0.8,
    priority: "high",
    status: "under_review",
    summary:
      "A minibus and a haulage truck are reported to have collided head-on on the A3 after the Headlands turn-off near Rusape. Traffic is reported stopped in both directions. An unverified claim says people are trapped.",
    vehicles: ["Minibus", "Haulage truck"],
    traffic: "Traffic reported stopped in both directions.",
    missing: [
      "Only one source. No second report, news item or official statement supports it yet.",
      "No kilometre marker or GPS point, so the position along the A3 is a guess.",
      "Time of the crash is not given. “Just now” cannot be assumed.",
      "Injury claim (“people trapped”) is unverified, so it is kept out of the draft summary.",
      "The attached photo has no location data and has not been checked.",
    ],
    createdCat: "2026-11-03 14:58",
    openedCat: "2026-11-03 16:20",
    evidence: [{ articleId: "art-001", role: "primary", eventId: "ev-001-1" }],
  },
  {
    id: "inc-0411",
    ref: "SR-0411",
    title: "Bus overturned near Kadoma",
    type: "rollover",
    severity: "serious",
    locationText: "A5 Harare–Bulawayo road, near Kadoma",
    roadName: "A5 Harare–Bulawayo road",
    province: "Mashonaland West",
    point: { lat: -18.333, lng: 29.917, accuracy: "town" },
    occurredCat: null,
    occurredNote: "Monday evening. Exact time not stated.",
    credibility: 0.68,
    credibilityRationale: "Two independent news reports agree on place and vehicle. Neither is an official statement.",
    risk: 0.55,
    priority: "urgent",
    status: "candidate",
    summary:
      "A long-distance bus is reported to have overturned on the A5 near Kadoma on Monday evening. Injured passengers are reported to have been taken to hospital. One lane was reported blocked.",
    vehicles: ["Long-distance bus"],
    traffic: "One lane blocked. Traffic slowed in both directions.",
    missing: [
      "Exact time and kilometre marker are not stated.",
      "Number of injured passengers is not given.",
      "Cause of the crash has not been established.",
    ],
    createdCat: "2026-11-02 21:15",
    evidence: [
      { articleId: "art-002", role: "primary", eventId: "ev-002-1" },
      { articleId: "art-003", role: "corroborating", eventId: "ev-003-1" },
    ],
  },
  {
    id: "inc-0410",
    ref: "SR-0410",
    title: "Pedestrian struck on Chitungwiza Road",
    type: "pedestrian_strike",
    severity: "unknown",
    locationText: "Chitungwiza Road, Harare",
    roadName: "Harare–Chitungwiza road",
    province: "Harare",
    point: { lat: -17.952, lng: 31.07, accuracy: "approximate" },
    occurredCat: "2026-11-01 16:40",
    occurredNote: "Around 16:40 on Sunday, per the article.",
    credibility: 0.45,
    credibilityRationale: "Single source citing unnamed witnesses. No official confirmation.",
    risk: 0.25,
    priority: "normal",
    status: "candidate",
    summary:
      "A pedestrian is reported to have been knocked down by a private car along Chitungwiza Road on Sunday afternoon and taken to hospital. The pedestrian's condition is not stated.",
    vehicles: ["Private car"],
    traffic: null,
    missing: [
      "Where along Chitungwiza Road is not stated.",
      "The pedestrian's condition is not stated.",
      "Single source, citing unnamed witnesses.",
    ],
    createdCat: "2026-11-01 17:50",
    evidence: [{ articleId: "art-004", role: "primary", eventId: "ev-004-1" }],
  },
  {
    id: "inc-0409",
    ref: "SR-0409",
    title: "Minibus and truck collision on the A4",
    type: "collision",
    severity: "serious",
    locationText: "A4 Masvingo–Beitbridge road",
    roadName: "A4 Masvingo–Beitbridge road",
    province: "Masvingo",
    point: { lat: -21.3, lng: 30.72, accuracy: "approximate" },
    occurredCat: "2026-11-01 08:05",
    occurredNote: "Around 08:05 on Sunday, per the article.",
    credibility: 0.5,
    credibilityRationale: "One community-run source. The position along the road is not given.",
    risk: 0.5,
    priority: "normal",
    status: "candidate",
    summary:
      "A minibus and a haulage truck are reported to have collided on the A4 Masvingo–Beitbridge road on Sunday morning. Passengers are reported injured. Numbers are not given.",
    vehicles: ["Minibus", "Haulage truck"],
    traffic: null,
    missing: [
      "Where on the Masvingo–Beitbridge road is not stated.",
      "Numbers and condition of injured passengers are not given.",
      "Single, community-run source in a multi-event roundup.",
    ],
    createdCat: "2026-11-01 20:20",
    evidence: [{ articleId: "art-005", role: "primary", eventId: "ev-005-2" }],
  },
  {
    id: "inc-0413",
    ref: "SR-0413",
    title: "Haulage truck fire near Chivhu",
    type: "vehicle_fire",
    severity: "minor",
    locationText: "A4 Harare–Beitbridge road, near Chivhu",
    roadName: "A4 Harare–Beitbridge road",
    province: "Mashonaland East",
    point: { lat: -19.017, lng: 30.883, accuracy: "town" },
    occurredCat: "2026-10-31 21:30",
    occurredNote: "About 21:30 on Saturday, per the article.",
    credibility: 0.6,
    credibilityRationale: "One community-run source. Plausible and specific, but not corroborated.",
    risk: 0.4,
    priority: "normal",
    status: "under_review",
    summary:
      "A haulage truck is reported to have caught fire on the A4 near Chivhu on Saturday night. The driver is reported to have escaped unhurt. One lane was closed for about two hours.",
    vehicles: ["Haulage truck"],
    traffic: "One lane closed for about two hours (since reopened, per the article).",
    missing: ["No kilometre marker.", "Single, community-run source."],
    createdCat: "2026-11-01 20:25",
    openedCat: "2026-11-02 09:20",
    evidence: [{ articleId: "art-005", role: "primary", eventId: "ev-005-1" }],
  },
  {
    id: "inc-0408",
    ref: "SR-0408",
    title: "Vehicle blocking a lane on the A5 near Gweru",
    type: "breakdown",
    severity: "minor",
    locationText: "A5 Harare–Bulawayo road, just outside Gweru",
    roadName: "A5 Harare–Bulawayo road",
    province: "Midlands",
    point: { lat: -19.43, lng: 29.83, accuracy: "approximate" },
    occurredCat: null,
    occurredNote: "Saturday morning.",
    credibility: 0.9,
    credibilityRationale: "Specific place and cause, consistent with the photo reference and a clear traffic effect.",
    risk: 0.2,
    priority: "normal",
    status: "published",
    summary: "A broken-down truck is reported to be blocking the left lane of the A5 just outside Gweru.",
    vehicles: ["Truck"],
    traffic: "Left lane blocked. Slow traffic in the open lane.",
    missing: [],
    createdCat: "2026-10-31 11:20",
    openedCat: "2026-10-31 12:00",
    evidence: [{ articleId: "art-006", role: "primary", eventId: "ev-006-1" }],
  },
  {
    id: "inc-0407",
    ref: "SR-0407",
    title: "Flooded low-level bridge near Hwange",
    type: "road_hazard",
    severity: "minor",
    locationText: "Low-level bridge on the A8 Bulawayo–Victoria Falls road, near Hwange",
    roadName: "A8 Bulawayo–Victoria Falls road",
    province: "Matabeleland North",
    point: { lat: -18.37, lng: 26.5, accuracy: "approximate" },
    occurredCat: null,
    occurredNote: "Friday morning, after overnight rain.",
    credibility: 0.85,
    credibilityRationale: "Two independent reports describe the same crossing and the same cause.",
    risk: 0.3,
    priority: "normal",
    status: "published",
    summary: "The low-level bridge on the A8 near Hwange is reported to be under water after overnight rain.",
    vehicles: [],
    traffic: "Light vehicles turning back. Some heavy vehicles waiting.",
    missing: ["No water depth or expected reopening time."],
    createdCat: "2026-10-30 07:30",
    openedCat: "2026-10-30 07:10",
    evidence: [
      { articleId: "art-007", role: "primary", eventId: "ev-007-1" },
      { articleId: "art-008", role: "corroborating", eventId: "ev-008-1" },
    ],
  },
  {
    id: "inc-0406",
    ref: "SR-0406",
    title: "Rear-end collision on the Plumtree road",
    type: "collision",
    severity: "minor",
    locationText: "Bulawayo–Plumtree road",
    roadName: "Bulawayo–Plumtree road",
    province: "Matabeleland South",
    point: { lat: -20.3, lng: 28.2, accuracy: "approximate" },
    occurredCat: "2026-10-12 12:00",
    occurredNote: "12 October, per the article.",
    credibility: 0.2,
    credibilityRationale: "A court follow-up about a crash three weeks earlier. Not a current event.",
    risk: 0.2,
    priority: "low",
    status: "rejected",
    summary: "A court follow-up on a rear-end collision on 12 October. Not a new incident.",
    vehicles: [],
    traffic: null,
    missing: ["The crash is three weeks old. This is a court follow-up, not a new event."],
    createdCat: "2026-10-30 02:20",
    openedCat: "2026-10-30 08:20",
    evidence: [{ articleId: "art-009", role: "primary", eventId: "ev-009-1" }],
  },
  {
    id: "inc-0405",
    ref: "SR-0405",
    title: "Livestock on the Mutare–Nyanga road",
    type: "road_hazard",
    severity: "unknown",
    locationText: "Mutare–Nyanga road",
    roadName: "Mutare–Nyanga road",
    province: "Manicaland",
    point: { lat: -18.6, lng: 32.7, accuracy: "approximate" },
    occurredCat: null,
    occurredNote: "Not stated (a recurring complaint).",
    credibility: 0.25,
    credibilityRationale: "A general complaint with no specific event, date or place.",
    risk: 0.15,
    priority: "low",
    status: "rejected",
    summary: "Residents complain that cattle wander onto the Mutare–Nyanga road. No specific event.",
    vehicles: [],
    traffic: null,
    missing: ["No specific event, date or place along the road."],
    createdCat: "2026-10-28 13:15",
    openedCat: "2026-10-28 15:00",
    evidence: [{ articleId: "art-010", role: "primary", eventId: "ev-010-1" }],
  },
];

/* ---------------------------------------------------------------- bulletins */

export interface BulletinSeed {
  id: string;
  incidentId: string;
  version: number;
  headline: string;
  body: string;
  by: "ai" | "tendai" | "rudo";
  atCat: string;
}

export const BULLETINS: BulletinSeed[] = [
  {
    id: "bul-0412-1",
    incidentId: "inc-0412",
    version: 1,
    headline: "Head-on collision reported on A3 near Rusape",
    body:
      "A head-on collision between a minibus and a haulage truck has been reported on the A3 Harare–Mutare road near Rusape. The report has not been independently confirmed. Traffic is reported to be stopped in both directions. Motorists should expect delays.",
    by: "ai",
    atCat: "2026-11-03 14:58",
  },
  {
    id: "bul-0411-1",
    incidentId: "inc-0411",
    version: 1,
    headline: "Bus overturned on A5 near Kadoma",
    body:
      "A long-distance bus is reported to have overturned on the A5 Harare–Bulawayo road near Kadoma on Monday evening. Passengers are reported to have been taken to hospital. One lane was reported blocked. Two news reports describe the incident; officials have not confirmed the details. Motorists should expect delays.",
    by: "ai",
    atCat: "2026-11-02 21:15",
  },
  {
    id: "bul-0410-1",
    incidentId: "inc-0410",
    version: 1,
    headline: "Pedestrian reported struck on Chitungwiza Road, Harare",
    body:
      "A pedestrian has been reported struck by a car on Chitungwiza Road in Harare on Sunday afternoon. The report comes from a single news source and has not been confirmed. Drivers and pedestrians are urged to take care in the area.",
    by: "ai",
    atCat: "2026-11-01 17:50",
  },
  {
    id: "bul-0409-1",
    incidentId: "inc-0409",
    version: 1,
    headline: "Minibus and truck collision reported on A4 Masvingo–Beitbridge road",
    body:
      "A collision between a minibus and a haulage truck has been reported on the A4 Masvingo–Beitbridge road on Sunday morning. The exact location along the road is not known and the report has not been confirmed. Drive with care and expect possible delays.",
    by: "ai",
    atCat: "2026-11-01 20:20",
  },
  {
    id: "bul-0413-1",
    incidentId: "inc-0413",
    version: 1,
    headline: "Haulage truck gutted by fire on A4 near Chivhu",
    body:
      "A haulage truck was reported to have been gutted by fire on the A4 near Chivhu on Saturday night. The driver escaped unhurt. One lane was closed for about two hours.",
    by: "rudo",
    atCat: "2026-11-02 08:50",
  },
  {
    id: "bul-0408-1",
    incidentId: "inc-0408",
    version: 1,
    headline: "Vehicle blocking a lane on the A5 near Gweru",
    body:
      "A vehicle is reported to be blocking one lane of the A5 Harare–Bulawayo road near Gweru. Drive carefully and expect slow traffic.",
    by: "tendai",
    atCat: "2026-10-31 12:05",
  },
  {
    id: "bul-0407-1",
    incidentId: "inc-0407",
    version: 1,
    headline: "Low-level bridge flooded on the A8 near Hwange",
    body:
      "The low-level bridge on the A8 Bulawayo–Victoria Falls road near Hwange is reported to be under water after heavy rain. Do not attempt to cross. Wait for the water to drop or use an alternative route.",
    by: "tendai",
    atCat: "2026-10-30 07:15",
  },
  {
    id: "bul-0406-1",
    incidentId: "inc-0406",
    version: 1,
    headline: "Rear-end collision on Bulawayo–Plumtree road",
    body: "A rear-end collision has been reported on the Bulawayo–Plumtree road.",
    by: "ai",
    atCat: "2026-10-30 02:20",
  },
  {
    id: "bul-0405-1",
    incidentId: "inc-0405",
    version: 1,
    headline: "Livestock on Mutare–Nyanga road",
    body: "Motorists on the Mutare–Nyanga road are reminded that livestock may be on the carriageway.",
    by: "ai",
    atCat: "2026-10-28 13:15",
  },
];

/* ------------------------------------------------------------------ reviews */

export interface ReviewSeed {
  id: string;
  incidentId: string;
  bulletinId: string | null;
  by: "tendai" | "rudo";
  decision: ReviewDecision;
  notes: string | null;
  atCat: string;
}

export const REVIEWS: ReviewSeed[] = [
  {
    id: "rev-0405",
    incidentId: "inc-0405",
    bulletinId: "bul-0405-1",
    by: "rudo",
    decision: "rejected",
    notes: "A general complaint about stray cattle with no specific event, date or place. Not an incident.",
    atCat: "2026-10-28 15:10",
  },
  {
    id: "rev-0406",
    incidentId: "inc-0406",
    bulletinId: "bul-0406-1",
    by: "tendai",
    decision: "rejected",
    notes: "Describes a crash on 12 October. A court follow-up, not a current incident.",
    atCat: "2026-10-30 08:30",
  },
  {
    id: "rev-0407",
    incidentId: "inc-0407",
    bulletinId: "bul-0407-1",
    by: "tendai",
    decision: "approved",
    notes: "Two independent reports agree. Wording says “reported”.",
    atCat: "2026-10-30 07:25",
  },
  {
    id: "rev-0408",
    incidentId: "inc-0408",
    bulletinId: "bul-0408-1",
    by: "tendai",
    decision: "approved",
    notes: null,
    atCat: "2026-10-31 12:10",
  },
  {
    id: "rev-0413",
    incidentId: "inc-0413",
    bulletinId: "bul-0413-1",
    by: "tendai",
    decision: "needs_changes",
    notes:
      "“Gutted” is not in the source; the article only says the truck caught fire. The lane has also reopened, so decide whether this still needs a public alert.",
    atCat: "2026-11-02 09:30",
  },
];

/* ------------------------------------------------------------------- alerts */

export interface AlertSeed {
  id: string;
  reference: string;
  incidentId: string;
  reviewId: string;
  bulletinId: string;
  publishedCat: string;
  channels: {
    channel: ChannelKind;
    status: "sent" | "failed" | "pending";
    attempts: { atCat: string; ok: boolean; error?: string }[];
  }[];
}

export const ALERTS: AlertSeed[] = [
  {
    id: "alert-a0408",
    reference: "A-0408",
    incidentId: "inc-0408",
    reviewId: "rev-0408",
    bulletinId: "bul-0408-1",
    publishedCat: "2026-10-31 12:12",
    channels: [
      { channel: "whatsapp", status: "sent", attempts: [{ atCat: "2026-10-31 12:12", ok: true }] },
      { channel: "sms", status: "sent", attempts: [{ atCat: "2026-10-31 12:13", ok: true }] },
      { channel: "web", status: "sent", attempts: [{ atCat: "2026-10-31 12:12", ok: true }] },
    ],
  },
  {
    id: "alert-a0407",
    reference: "A-0407",
    incidentId: "inc-0407",
    reviewId: "rev-0407",
    bulletinId: "bul-0407-1",
    publishedCat: "2026-10-30 07:26",
    channels: [
      { channel: "whatsapp", status: "sent", attempts: [{ atCat: "2026-10-30 07:26", ok: true }] },
      {
        channel: "sms",
        status: "failed",
        attempts: [
          { atCat: "2026-10-30 07:27", ok: false, error: "Simulated gateway timeout" },
          { atCat: "2026-10-30 07:42", ok: false, error: "Simulated gateway timeout" },
        ],
      },
      { channel: "web", status: "sent", attempts: [{ atCat: "2026-10-30 07:26", ok: true }] },
    ],
  },
];
