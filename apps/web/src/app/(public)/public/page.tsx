import Link from "next/link";
import { Suspense } from "react";
import { Bell, ListChecks, Route as RouteIcon } from "lucide-react";
import { AlertCard } from "@/components/public/alert-card";
import { ErrorNotice } from "@/components/public/site-chrome";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { attempt, formatWhen, publicApi } from "@/lib/public-api/client";

async function LatestAlerts() {
  const { data: summary, error } = await attempt(() => publicApi.summary());
  if (error) return <ErrorNotice message={error.message} />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        {summary.recent_alert_count} published notice{summary.recent_alert_count === 1 ? "" : "s"} in the last{" "}
        {summary.window_days} days.
        {summary.last_updated ? <> Last update {formatWhen(summary.last_updated)}.</> : null}
      </p>
      {summary.latest_alerts.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">
          There are no published notices right now. This does not mean roads are free of hazards.
        </p>
      ) : (
        summary.latest_alerts.map((a) => <AlertCard key={a.id} alert={a} />)
      )}
    </div>
  );
}

export default function PublicHome() {
  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Know the road ahead.</h1>
        <p className="max-w-xl text-slate-700">
          Reviewed road safety notices for Zimbabwe, and a simple way to check your journey.
        </p>
        <form action="/public/routes" method="get" className="grid max-w-xl gap-3 rounded-xl border border-slate-200 bg-white p-4">
          <label className="grid gap-1 text-sm font-medium">
            From
            <Input name="from" placeholder="e.g. Harare" maxLength={200} className="h-11" autoComplete="off" />
          </label>
          <label className="grid gap-1 text-sm font-medium">
            To
            <Input name="to" placeholder="e.g. Mutare" maxLength={200} className="h-11" autoComplete="off" />
          </label>
          <Button type="submit" size="lg">
            <RouteIcon /> Plan Route
          </Button>
        </form>
        <div className="flex flex-wrap gap-3">
          <Button asChild variant="outline" size="lg">
            <Link href="/public/alerts">
              <ListChecks /> View Road Alerts
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/public/subscribe">
              <Bell /> Subscribe to Alerts
            </Link>
          </Button>
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="latest">
        <h2 id="latest" className="text-xl font-semibold text-slate-900">
          Latest road safety notices
        </h2>
        <Suspense fallback={<p className="text-sm text-slate-500">Loading notices…</p>}>
          <LatestAlerts />
        </Suspense>
      </section>

      <section className="max-w-2xl space-y-2 text-sm text-slate-700">
        <h2 className="text-lg font-semibold text-slate-900">About SafeRouteZW</h2>
        <p>
          SafeRouteZW collects road incident reports from news and official sources. A human editor reviews each report and
          decides whether to publish it. Only published notices appear here.
        </p>
        <p>
          Notices can be incomplete, delayed or out of date, and locations may be approximate. Route times are estimates
          without live traffic. If no alert appears on your route, that is not proof the road is safe.
        </p>
      </section>
    </div>
  );
}
