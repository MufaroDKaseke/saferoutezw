import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type IconTone = "slate" | "amber" | "emerald" | "red" | "indigo" | "navy";

const ICON_TONE: Record<IconTone, string> = {
  slate: "bg-slate-100 text-slate-600",
  amber: "bg-amber-100 text-amber-700",
  emerald: "bg-emerald-100 text-emerald-700",
  red: "bg-red-100 text-red-700",
  indigo: "bg-indigo-100 text-indigo-700",
  navy: "bg-slate-900 text-white",
};

export function KpiCard({
  title,
  value,
  icon: Icon,
  tone = "slate",
  hint,
  href,
  emphasis = false,
  className,
}: {
  title: string;
  value: React.ReactNode;
  icon: LucideIcon;
  tone?: IconTone;
  /** Short line under the number. Plain text; put the key phrase in <strong>. */
  hint?: React.ReactNode;
  href?: string;
  /** Outline the card in the tone colour, for example for delivery failures. */
  emphasis?: boolean;
  className?: string;
}) {
  const body = (
    <Card
      className={cn(
        "h-full gap-3 transition-shadow",
        href && "hover:shadow-md",
        emphasis && "ring-red-300",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3 px-(--card-spacing)">
        <p className="text-sm font-medium text-slate-600">{title}</p>
        <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", ICON_TONE[tone])}>
          <Icon className="size-4" aria-hidden />
        </span>
      </div>
      <div className="px-(--card-spacing)">
        <p className="tnum text-4xl leading-none font-bold tracking-tight text-foreground">{value}</p>
        {hint ? <p className="mt-2 text-xs text-slate-600">{hint}</p> : null}
      </div>
    </Card>
  );
  if (!href) return body;
  return (
    <Link href={href} className="block rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2">
      {body}
    </Link>
  );
}

export function KpiCardSkeleton() {
  return (
    <Card className="gap-3">
      <div className="flex items-start justify-between px-(--card-spacing)">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="size-8 rounded-lg" />
      </div>
      <div className="space-y-2 px-(--card-spacing)">
        <Skeleton className="h-9 w-16" />
        <Skeleton className="h-3 w-40" />
      </div>
    </Card>
  );
}
