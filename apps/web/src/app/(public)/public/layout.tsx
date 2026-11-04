import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "@/components/public/site-chrome";

export const metadata: Metadata = {
  title: { default: "SafeRouteZW · Know the road ahead", template: "%s · SafeRouteZW" },
  description: "Reviewed road safety alerts, a route planner and SMS or WhatsApp alerts for Zimbabwe.",
};

/** Public layout: no newsroom sidebar, no login. Pages own their width so the home hero can run edge to edge. */
export default function PublicLayout({ children }: LayoutProps<"/public">) {
  return (
    <div className="min-h-screen bg-slate-50">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-white focus:p-2">
        Skip to content
      </a>
      <SiteHeader />
      <main id="main">{children}</main>
      <SiteFooter />
    </div>
  );
}
