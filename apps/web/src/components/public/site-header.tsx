"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Bell, House, ListChecks, Map as MapIcon, Menu, Route as RouteIcon, Truck, UserRound, X, Newspaper } from "lucide-react";
import { BrandMark, Wordmark } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export const PUBLIC_NAV = [
  { href: "/public", label: "Home", icon: House, exact: true },
  { href: "/public/alerts", label: "Road Alerts", icon: ListChecks },
  { href: "/public/map", label: "Safety Map", icon: MapIcon },
  { href: "/public/routes", label: "Plan a Route", icon: RouteIcon },
  { href: "/public/transport", label: "Transport News", icon: Newspaper },
  { href: "/public/operators", label: "Transport Operators", icon: Truck },
] as const;

function isActive(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur print:hidden">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-2 px-4 sm:px-6 lg:gap-6">
        <Link href="/public" className="flex min-h-11 items-center gap-2" aria-label="SafeRouteZW home">
          <BrandMark className="size-9" />
          <Wordmark tone="dark" className="text-lg" />
        </Link>

        <nav aria-label="Main" className="ml-2 hidden flex-1 items-center gap-0.5 lg:flex">
          {PUBLIC_NAV.map((item) => {
            const active = isActive(pathname, item.href, "exact" in item ? item.exact : false);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center rounded-lg px-3 text-[15px] font-medium transition-colors",
                  active ? "bg-emerald-50 font-semibold text-emerald-900" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <Button asChild variant="approve" size="lg" className="px-3.5 sm:px-4">
            <Link href="/public/subscribe">
              <Bell /> Get alerts
            </Link>
          </Button>

          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon-lg" className="lg:hidden" aria-label="Open menu">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" showCloseButton={false} className="w-[88%] max-w-sm gap-0 p-0">
              <div className="relative flex min-h-16 items-center border-b border-slate-200 px-4 pr-16">
                <SheetClose asChild>
                  <Button variant="ghost" size="icon-lg" className="absolute top-2.5 right-3" aria-label="Close menu">
                    <X className="size-5" />
                  </Button>
                </SheetClose>
                <SheetTitle className="text-base font-bold">Menu</SheetTitle>
                <SheetDescription className="sr-only">Main navigation for SafeRouteZW</SheetDescription>
              </div>
              <nav aria-label="Main" className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
                {PUBLIC_NAV.map((item) => {
                  const active = isActive(pathname, item.href, "exact" in item ? item.exact : false);
                  return (
                    <SheetClose asChild key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "flex min-h-14 items-center gap-3 rounded-xl px-3 text-base font-semibold",
                          active ? "bg-emerald-50 text-emerald-900" : "text-slate-800 hover:bg-slate-100",
                        )}
                      >
                        <item.icon className="size-5" aria-hidden />
                        {item.label}
                      </Link>
                    </SheetClose>
                  );
                })}
                <div className="my-2 border-t border-slate-200" />
                <SheetClose asChild>
                  <Link href="/public/subscription/manage" className="flex min-h-12 items-center gap-3 rounded-xl px-3 text-[15px] font-medium text-slate-700 hover:bg-slate-100">
                    <UserRound className="size-5" aria-hidden /> Manage subscription
                  </Link>
                </SheetClose>
              </nav>
              <div className="space-y-3 border-t border-slate-200 p-4">
                <SheetClose asChild>
                  <Button asChild variant="approve" size="lg" className="h-12 w-full text-base">
                    <Link href="/public/subscribe">
                      <Bell /> Get alerts
                    </Link>
                  </Button>
                </SheetClose>
                <p className="text-xs text-slate-600">
                  SafeRouteZW shares reviewed road notices. No alert on your route does not mean the road is safe.
                </p>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
