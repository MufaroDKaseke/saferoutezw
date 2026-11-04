"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { ArrowUpDown, MapPin, Navigation, Route as RouteIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

const EXAMPLES: Array<[string, string]> = [
  ["Harare", "Mutare"],
  ["Harare", "Bulawayo"],
  ["Bulawayo", "Victoria Falls"],
];

/**
 * The primary action on the home page. It is a plain GET form to /public/routes, so it still works
 * without JavaScript; the swap button is the only enhancement.
 */
export function JourneyForm() {
  const id = useId();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const field =
    "h-12 w-full rounded-xl border border-input bg-white pr-14 pl-11 text-base text-slate-900 outline-none placeholder:text-slate-500 focus-visible:border-emerald-600 focus-visible:ring-3 focus-visible:ring-emerald-600/30";

  return (
    <form action="/public/routes" method="get" className="space-y-4 rounded-2xl bg-white p-4 text-slate-900 shadow-xl shadow-black/30 sm:p-5">
      <div className="relative grid gap-3">
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-from`} className="text-sm font-semibold">
            From
          </label>
          <div className="relative">
            <Navigation className="pointer-events-none absolute top-3.5 left-3.5 size-5 text-emerald-700" aria-hidden />
            <input id={`${id}-from`} name="from" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="e.g. Harare" maxLength={200} autoComplete="off" className={field} />
          </div>
        </div>
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-to`} className="text-sm font-semibold">
            To
          </label>
          <div className="relative">
            <MapPin className="pointer-events-none absolute top-3.5 left-3.5 size-5 text-emerald-700" aria-hidden />
            <input id={`${id}-to`} name="to" value={to} onChange={(e) => setTo(e.target.value)} placeholder="e.g. Mutare" maxLength={200} autoComplete="off" className={field} />
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon-lg"
          aria-label="Swap From and To"
          className="absolute top-1/2 right-1.5 mt-1 size-11 -translate-y-1/2 rounded-full shadow-sm"
          onClick={() => {
            setFrom(to);
            setTo(from);
          }}
        >
          <ArrowUpDown className="size-4" />
        </Button>
      </div>
      <Button type="submit" variant="approve" size="lg" className="h-13 w-full rounded-xl text-base">
        <RouteIcon className="size-5" /> Plan Journey
      </Button>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-600">Try</span>
        {EXAMPLES.map(([a, b]) => (
          <Link
            key={`${a}-${b}`}
            href={`/public/routes?from=${encodeURIComponent(a)}&to=${encodeURIComponent(b)}`}
            className="inline-flex min-h-9 items-center rounded-full border border-slate-300 px-3 font-medium text-slate-800 hover:bg-slate-100"
          >
            {a} to {b}
          </Link>
        ))}
      </div>
    </form>
  );
}
