"use client";

import Link from "next/link";
import { useState } from "react";
import { Bell, ClipboardCheck, Cpu, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { QueryError } from "@/components/shared/states";
import { useResource } from "@/hooks/use-resource";
import { listAlerts } from "@/lib/api/alerts";
import { getBacklog } from "@/lib/api/processing";
import { getReviewCounts } from "@/lib/api/reviews";

/**
 * "Notifications" here means items that need a person, computed from real
 * counts (reviews waiting, failed processing, failed deliveries). There are no
 * invented alerts.
 */
export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const attention = useResource("attention", async () => {
    const [reviews, backlog, failed] = await Promise.all([
      getReviewCounts(),
      getBacklog(),
      listAlerts({ state: "delivery_failed", pageSize: 1 }),
    ]);
    return {
      reviews: reviews.pending + reviews.needs_changes,
      processing: backlog.failedNeedingAttention,
      deliveries: failed.total,
    };
  });

  const total = attention.data ? attention.data.reviews + attention.data.processing + attention.data.deliveries : 0;
  const items = attention.data
    ? [
        { href: "/reviews", icon: ClipboardCheck, count: attention.data.reviews, text: (n: number) => `${n} ${n === 1 ? "report is" : "reports are"} waiting for an editor` },
        { href: "/processing", icon: Cpu, count: attention.data.processing, text: (n: number) => `${n} ${n === 1 ? "article needs" : "articles need"} a processing retry` },
        { href: "/alerts", icon: Send, count: attention.data.deliveries, text: (n: number) => `${n} ${n === 1 ? "alert has" : "alerts have"} a failed delivery` },
      ].filter((i) => i.count > 0)
    : [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon-lg" className="relative" aria-label={total ? `Notifications, ${total} need attention` : "Notifications"}>
          <Bell aria-hidden />
          {total > 0 ? <span className="absolute top-2 right-2.5 size-2 rounded-full bg-amber-500 ring-2 ring-white" aria-hidden /> : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 gap-3 p-4">
        <h2 className="text-sm font-bold">Needs attention</h2>
        {attention.error ? (
          <QueryError error={attention.error} onRetry={attention.refetch} />
        ) : !attention.data ? (
          <p className="text-sm text-slate-600">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-600">Nothing is waiting for you.</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="flex items-start gap-3 rounded-lg p-2 text-sm hover:bg-slate-50"
                >
                  <item.icon className="mt-0.5 size-4 shrink-0 text-slate-500" aria-hidden />
                  <span>{item.text(item.count)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
