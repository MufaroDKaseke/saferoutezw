import Image from "next/image";
import { Route } from "lucide-react";
import { isNewsroomMode } from "@/lib/app-mode";
import { cn } from "@/lib/utils";

/** The supplied station artwork, kept intact and sized for its container. */
export function NustFmLogo({ className, sizes = "(max-width: 1023px) 280px, 420px" }: { className?: string; sizes?: string }) {
  return (
    <Image
      src="/branding/nust-fm-logo.jpg"
      width={2699}
      height={761}
      alt="NUST FM 101.1 — Feel the vibe!"
      sizes={sizes}
      loading="eager"
      className={cn("h-auto w-full", className)}
    />
  );
}

/** Compact mark; the newsroom uses a viewport onto the crest in the supplied logo. */
export function BrandMark({ className }: { className?: string }) {
  if (isNewsroomMode) {
    return (
      <span className={cn("flex size-9 shrink-0 items-center justify-center", className)} aria-hidden>
        <svg viewBox="65 145 480 590" className="size-full" focusable="false">
          <image href="/branding/nust-fm-logo.jpg" width="2699" height="761" />
        </svg>
      </span>
    );
  }
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-emerald-500 text-emerald-950",
        className,
      )}
      aria-hidden
    >
      <Route className="size-5" strokeWidth={2.4} />
    </span>
  );
}

export function Wordmark({ tone = "light", className }: { tone?: "light" | "dark"; className?: string }) {
  const accent = isNewsroomMode
    ? (tone === "light" ? "text-brand-sky" : "text-brand-blue")
    : (tone === "light" ? "text-emerald-400" : "text-emerald-700");
  return (
    <span className={cn("text-[17px] leading-none font-bold tracking-tight", className)}>
      <span className={tone === "light" ? "text-white" : "text-slate-900"}>{isNewsroomMode ? "NUST " : "SafeRoute"}</span>
      <span className={accent}>
        {isNewsroomMode ? "FM" : "ZW"}
      </span>
    </span>
  );
}
