import {
  Activity,
  BellRing,
  ClipboardCheck,
  Cpu,
  Database,
  Library,
  LayoutDashboard,
  Map,
  Newspaper,
  Settings,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

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

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ title: "Dashboard", href: "/dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Intelligence",
    items: [
      { title: "News Monitor", href: "/news", icon: Newspaper },
      { title: "Transport Intelligence", href: "/intelligence", icon: Library },
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

/** Section name and group for the breadcrumb, keyed by the first path segment. */
export const SECTION_BY_SEGMENT: Record<string, { group: string; title: string; href: string }> = Object.fromEntries(
  NAV_GROUPS.flatMap((g) =>
    g.items.map((i) => [i.href.replace(/^\//, ""), { group: g.label, title: i.title, href: i.href }] as const),
  ),
);

export function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
