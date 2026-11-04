import type { Blackspot } from "@/types";

/**
 * SYNTHETIC blackspots for demonstration only. These are NOT official records
 * and the coordinates are illustrative placements near the named roads and
 * towns. A verified dataset would come from an official or academic source and
 * be loaded through the backend (data/blackspots is intentionally private).
 */
type BlackspotSeed = Omit<Blackspot, "nearbyIncidentCount" | "synthetic" | "dataSourceName"> & {
  notes: string | null;
};

const SEEDS: BlackspotSeed[] = [
  {
    id: "bs-d01",
    code: "D-01",
    name: "Headlands turn-off to Rusape stretch",
    roadName: "A3 Harare–Mutare road",
    province: "Manicaland",
    riskLevel: "high",
    point: { lat: -18.4895, lng: 32.0625, accuracy: "approximate", synthetic: true },
    radiusKm: 3,
    observationPeriod: { from: "2019-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A3-01",
    notes: "Illustrative placement. Long straights with heavy minibus and haulage traffic.",
  },
  {
    id: "bs-d02",
    code: "D-02",
    name: "Kadoma approach",
    roadName: "A5 Harare–Bulawayo road",
    province: "Mashonaland West",
    riskLevel: "high",
    point: { lat: -18.38, lng: 29.82, accuracy: "approximate", synthetic: true },
    radiusKm: 3,
    observationPeriod: { from: "2019-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A5-02",
    notes: null,
  },
  {
    id: "bs-d03",
    code: "D-03",
    name: "Gweru southern bypass",
    roadName: "A5 Harare–Bulawayo road",
    province: "Midlands",
    riskLevel: "high",
    point: { lat: -19.49, lng: 29.79, accuracy: "approximate", synthetic: true },
    radiusKm: 2.5,
    observationPeriod: { from: "2019-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A5-03",
    notes: null,
  },
  {
    id: "bs-d04",
    code: "D-04",
    name: "Masvingo–Beitbridge mid-section",
    roadName: "A4 Masvingo–Beitbridge road",
    province: "Masvingo",
    riskLevel: "high",
    point: { lat: -20.95, lng: 30.65, accuracy: "approximate", synthetic: true },
    radiusKm: 4,
    observationPeriod: { from: "2020-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A4-04",
    notes: "Heavy cross-border haulage.",
  },
  {
    id: "bs-d05",
    code: "D-05",
    name: "Chinhoyi western approach",
    roadName: "A1 Harare–Chirundu road",
    province: "Mashonaland West",
    riskLevel: "medium",
    point: { lat: -17.37, lng: 30.12, accuracy: "approximate", synthetic: true },
    radiusKm: 2.5,
    observationPeriod: { from: "2020-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A1-05",
    notes: null,
  },
  {
    id: "bs-d06",
    code: "D-06",
    name: "Hwange low-level crossings",
    roadName: "A8 Bulawayo–Victoria Falls road",
    province: "Matabeleland North",
    riskLevel: "medium",
    point: { lat: -18.45, lng: 26.55, accuracy: "approximate", synthetic: true },
    radiusKm: 3,
    observationPeriod: { from: "2021-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-A8-06",
    notes: "Seasonal flooding rather than collision density.",
  },
  {
    id: "bs-d07",
    code: "D-07",
    name: "Chitungwiza Road pedestrian corridor",
    roadName: "Harare–Chitungwiza road",
    province: "Harare",
    riskLevel: "high",
    point: { lat: -17.935, lng: 31.075, accuracy: "approximate", synthetic: true },
    radiusKm: 2,
    observationPeriod: { from: "2019-01-01", to: "2023-12-31" },
    sourceReference: "DEMO-REF-HCZ-07",
    notes: "Pedestrian-heavy commuter corridor.",
  },
];

export const BLACKSPOT_SEEDS = SEEDS;
export const BLACKSPOT_DATA_SOURCE = "Synthetic demo dataset (not official)";
