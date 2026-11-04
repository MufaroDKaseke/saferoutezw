import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/public/site-chrome";
import { RoutePlanner } from "@/components/public/route-planner";

export const metadata: Metadata = { title: "Operator journey planner" };

export default function OperatorsPage() {
  return (
    <PageShell
      title="Operator journey planner"
      intro="Plan a journey with up to five stops in the order you give. Print a safety briefing for your driver. No sign-up needed."
    >
      <Suspense fallback={<p className="text-sm text-slate-500">Loading planner…</p>}>
        <RoutePlanner operator />
      </Suspense>
    </PageShell>
  );
}
