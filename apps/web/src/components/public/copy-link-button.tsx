"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Copies the current page address. Reports the result in text, not only with an icon. */
export function CopyLinkButton({ className }: { className?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("copied");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      setState("failed");
    }
  }

  return (
    <div className={className}>
      <Button type="button" variant="outline" size="lg" className="w-full" onClick={copy}>
        {state === "copied" ? <Check /> : <Copy />} {state === "copied" ? "Link copied" : "Copy link"}
      </Button>
      <p role="status" className="mt-1.5 min-h-4 text-xs text-slate-600">
        {state === "failed" ? "Copying is not available in this browser. Copy the address from the address bar." : ""}
      </p>
    </div>
  );
}
