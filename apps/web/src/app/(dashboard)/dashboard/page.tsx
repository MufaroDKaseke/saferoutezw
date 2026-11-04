import type { Metadata } from "next";
import { Suspense } from "react";
import { DashboardView } from "@/components/dashboard/dashboard-view";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  // The view shows today's date (`new Date()` in API mode), which must be read per visit, not at prerender.
  return (
    <Suspense fallback={<p className="text-sm text-slate-600">Loading the dashboard…</p>}>
      <DashboardView />
    </Suspense>
  );
}
