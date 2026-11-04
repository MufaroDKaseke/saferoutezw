import type { Metadata } from "next";
import { Suspense } from "react";
import { PageShell } from "@/components/public/site-chrome";
import { RoutePlanner } from "@/components/public/route-planner";

export const metadata: Metadata = { title: "Transport Operators" };

export default function OperatorsPage() {
  return (
    <PageShell
      title="Transport Operators"
      intro="For bus, kombi and truck operators and dispatchers. Plan a trip with up to five stops in the order you give, check hazards along the whole route and print a briefing for your driver. No sign-up needed."
    >
      <Suspense fallback={<p className="text-sm text-slate-500">Loading planner…</p>}>
        <RoutePlanner operator />
      </Suspense>
    </PageShell>
  );
}
