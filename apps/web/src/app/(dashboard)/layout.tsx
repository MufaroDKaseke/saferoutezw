import { Suspense } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { SessionGuard } from "@/components/layout/session-guard";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to main content
      </a>
      <SessionGuard />
      {/* usePathname() is request-time data under Cache Components, so it streams in behind Suspense. */}
      <Suspense fallback={<div className="hidden w-(--sidebar-width) shrink-0 bg-sidebar md:block" aria-hidden />}>
        <AppSidebar />
      </Suspense>
      <SidebarInset className="min-w-0 bg-background">
        <Suspense fallback={<div className="h-[65px] border-b bg-card" aria-hidden />}>
          <AppHeader />
        </Suspense>
        <main id="main-content" className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
