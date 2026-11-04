import type { DemoUser, Source } from "@/types";

/** The demo session user. Not a real account; there is no authentication backend yet. */
export const DEMO_USER: DemoUser = {
  id: "u-tendai",
  name: "Tendai Moyo",
  email: "tendai.moyo@demo.saferoutezw.example",
  role: "editor",
  title: "Senior editor",
  isDemo: true,
};

export const OTHER_REVIEWERS = [
  { id: "u-rudo", name: "Rudo Chikafu", role: "editor" as const },
] as const;

export const AI_ACTOR = { id: "u-ai", name: "SafeRouteZW AI" } as const;
export const SYSTEM_ACTOR = { id: "u-system", name: "System" } as const;

/**
 * Fictional publishers. Feed URLs use the reserved `.example` TLD, so nothing
 * here can be mistaken for, or accidentally fetch from, a real publisher.
 */
export const SOURCES: Source[] = [
  {
    id: "src-courier",
    name: "Harare Daily Courier",
    kind: "rss",
    feedUrl: "https://harare-daily-courier.example/feed",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: "Headline and excerpt reuse permitted with attribution (demo).",
    synthetic: true,
  },
  {
    id: "src-midlands",
    name: "Midlands Mirror",
    kind: "rss",
    feedUrl: "https://midlands-mirror.example/rss.xml",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: "Attribution required (demo).",
    synthetic: true,
  },
  {
    id: "src-bulawayo",
    name: "Bulawayo Metro News",
    kind: "rss",
    feedUrl: "https://bulawayo-metro-news.example/feed/",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: null,
    synthetic: true,
  },
  {
    id: "src-eastern",
    name: "Eastern Highlands Post",
    kind: "rss",
    feedUrl: "https://eastern-highlands-post.example/feed",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: "Excerpts only; link back to the original (demo).",
    synthetic: true,
  },
  {
    id: "src-roadwatch",
    name: "Roadwatch Zimbabwe Bulletin",
    kind: "rss",
    feedUrl: "https://roadwatch-zimbabwe.example/bulletin.rss",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "community",
    rightsNotes: "Community-run bulletin. Treat as unverified until corroborated (demo).",
    synthetic: true,
  },
  {
    id: "src-authority",
    name: "National Road Authority Notices",
    kind: "rss",
    feedUrl: "https://road-authority-notices.example/notices.xml",
    enabled: true,
    pollIntervalSeconds: 300,
    verificationTier: "official",
    rightsNotes: "Public notices (demo).",
    synthetic: true,
  },
  {
    id: "src-lowveld",
    name: "Lowveld Leader",
    kind: "rss",
    feedUrl: "https://lowveld-leader.example/feed",
    enabled: false,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: "Paused while the publisher migrates its website (demo).",
    synthetic: true,
  },
  {
    id: "src-masvingo",
    name: "Masvingo Sun",
    kind: "rss",
    feedUrl: "https://masvingo-sun.example/rss",
    enabled: true,
    pollIntervalSeconds: 180,
    verificationTier: "established_media",
    rightsNotes: null,
    synthetic: true,
  },
];
