import { Radio, Route } from "lucide-react";
import { isNewsroomMode } from "@/lib/app-mode";
import { cn } from "@/lib/utils";

/** SafeRouteZW mark: emerald rounded square with a route glyph. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-emerald-500 text-emerald-950",
        className,
      )}
      aria-hidden
    >
      {isNewsroomMode ? <Radio className="size-5" strokeWidth={2.4} /> : <Route className="size-5" strokeWidth={2.4} />}
    </span>
  );
}

export function Wordmark({ tone = "light", className }: { tone?: "light" | "dark"; className?: string }) {
  return (
    <span className={cn("text-[17px] leading-none font-bold tracking-tight", className)}>
      <span className={tone === "light" ? "text-white" : "text-slate-900"}>{isNewsroomMode ? "NUST " : "SafeRoute"}</span>
      <span className={tone === "light" ? "text-emerald-400" : "text-emerald-700"}>{isNewsroomMode ? "FM" : "ZW"}</span>
    </span>
  );
}
