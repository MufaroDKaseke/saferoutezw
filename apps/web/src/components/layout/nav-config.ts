import {
  Activity,
  Archive,
  BellRing,
  ClipboardCheck,
  Cpu,
  Database,
  LayoutDashboard,
  Library,
  Map,
  Mic,
  Newspaper,
  NotebookPen,
  Radio,
  Settings,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { APP_MODE, type AppMode } from "@/lib/app-mode";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  /** Shows the pending-review count as a badge. */
  badge?: "pendingReviews";
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

const ROAD_NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ title: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Intelligence",
    items: [
      { title: "News Monitor", href: "/news", icon: Newspaper },
      { title: "Intelligence", href: "/intelligence", icon: Library },
      { title: "Incidents", href: "/incidents", icon: Activity },
      { title: "Safety Map", href: "/map", icon: Map },
      { title: "Historical Blackspots", href: "/blackspots", icon: TriangleAlert },
    ],
  },
  {
    label: "Editorial",
    items: [
      { title: "Review Queue", href: "/reviews", icon: ClipboardCheck, badge: "pendingReviews" },
      { title: "Public Alerts", href: "/alerts", icon: BellRing },
    ],
  },
  {
    label: "Operations",
    items: [
      { title: "Data Sources", href: "/sources", icon: Database },
      { title: "Processing Activity", href: "/processing", icon: Cpu },
      { title: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

/** NUST FM: collect, classify and read the news, then turn it into stories. No road-safety pages. */
const NEWSROOM_NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ title: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Newsroom",
    items: [
      { title: "News Monitor", href: "/news", icon: Newspaper },
      { title: "Stories", href: "/stories", icon: NotebookPen },
      { title: "Bulletins", href: "/bulletins", icon: Radio },
      { title: "Studio", href: "/studio", icon: Mic },
      { title: "Archive", href: "/archive", icon: Archive },
    ],
  },
  {
    label: "Operations",
    items: [
      { title: "Data Sources", href: "/sources", icon: Database },
      { title: "Processing Activity", href: "/processing", icon: Cpu },
      { title: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

/** The menu for a product mode. Taking the mode as an argument keeps it testable. */
export function getNavGroups(mode: AppMode): NavGroup[] {
  return mode === "nust_newsroom" ? NEWSROOM_NAV_GROUPS : ROAD_NAV_GROUPS;
}

export function getSectionBySegment(mode: AppMode): Record<string, { group: string; title: string; href: string }> {
  return Object.fromEntries(
    getNavGroups(mode).flatMap((g) =>
      g.items.map((i) => [i.href.replace(/^\//, ""), { group: g.label, title: i.title, href: i.href }] as const),
    ),
  );
}

/** The menu of this build. */
export const NAV_GROUPS: NavGroup[] = getNavGroups(APP_MODE);

/** Section name and group for the breadcrumb, keyed by the first path segment. */
export const SECTION_BY_SEGMENT = getSectionBySegment(APP_MODE);

export function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
