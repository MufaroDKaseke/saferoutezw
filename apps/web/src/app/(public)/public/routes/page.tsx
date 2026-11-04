import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/public/site-chrome";
import { RoutePlanner } from "@/components/public/route-planner";

export const metadata: Metadata = { title: "Plan a route" };

export default function RoutesPage() {
  return (
    <PageShell
      title="Plan a route"
      intro="Find a driving route and see the published road alerts near it. Times are estimates without live traffic."
    >
      <Suspense fallback={<p className="text-sm text-slate-500">Loading planner…</p>}>
        <RoutePlanner />
      </Suspense>
    </PageShell>
  );
}
