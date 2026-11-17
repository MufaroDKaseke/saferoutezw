"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle, LogOut } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { useDemoSession } from "@/hooks/use-demo-session";
import { useResource } from "@/hooks/use-resource";
import { getDataMode } from "@/lib/api/config";
import { getPendingReviewCount } from "@/lib/api/reviews";
import { BrandMark, NustFmLogo, Wordmark } from "./brand";
import { isNewsroomMode } from "@/lib/app-mode";
import { NAV_GROUPS, isActivePath } from "./nav-config";

const ITEM_CLASS =
  "h-9 gap-3 rounded-lg px-3 text-sm font-medium text-slate-300 hover:bg-white/5 hover:text-white data-[active=true]:bg-sidebar-accent data-[active=true]:text-white data-[active=true]:font-semibold [&>svg]:size-5";

function ModeCard() {
  if (getDataMode() !== "mock") return null;
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 group-data-[collapsible=icon]:hidden">
      <p className="flex items-center gap-1.5 text-[13px] font-semibold text-amber-400">
        <AlertTriangle className="size-4" aria-hidden /> Demo mode
      </p>
      <p className="mt-1 text-xs leading-relaxed text-slate-400">
        Synthetic data. Nothing here is a real incident, and no alert is ever sent.
      </p>
    </div>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const { user, signOut } = useDemoSession();
  // The review queue is a road-safety feature: the newsroom never asks for it.
  const pending = useResource("sidebar:pending-reviews", () => (isNewsroomMode ? Promise.resolve(0) : getPendingReviewCount()));
  const pendingCount = pending.error ? null : (pending.data ?? null);

  return (
    <Sidebar collapsible="icon" className="border-r-0">
      <SidebarHeader className="px-4 pt-4 pb-2 group-data-[collapsible=icon]:px-2">
        <Link
          href="/dashboard"
          className="flex items-center gap-3 rounded-lg focus-visible:outline-2"
          aria-label={isNewsroomMode ? "NUST FM dashboard" : "SafeRouteZW dashboard"}
          onClick={() => setOpenMobile(false)}
        >
          {isNewsroomMode ? (
            <>
              <NustFmLogo sizes="224px" className="rounded-md group-data-[collapsible=icon]:hidden" />
              <BrandMark className="hidden size-8 group-data-[collapsible=icon]:flex" />
            </>
          ) : (
            <>
              <BrandMark />
              <span className="flex flex-col gap-1.5 group-data-[collapsible=icon]:hidden">
                <Wordmark />
                <span className="text-[11.5px] leading-none text-slate-400">Road Safety Intelligence</span>
              </span>
            </>
          )}
        </Link>
        {isNewsroomMode ? (
          <span className="mt-1 px-2 text-[10px] font-medium tracking-[0.18em] text-brand-sky uppercase group-data-[collapsible=icon]:hidden">
            Newsroom workspace
          </span>
        ) : null}
      </SidebarHeader>

      <SidebarContent className="gap-0 px-2 py-1">
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.label} className="py-1">
            <SidebarGroupLabel className="h-7 px-3 text-[11.5px] font-semibold tracking-[0.08em] text-slate-500 uppercase">
              {group.label}
            </SidebarGroupLabel>
            <SidebarMenu>
              {group.items.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActivePath(pathname, item.href)}
                    tooltip={item.title}
                    className={ITEM_CLASS}
                  >
                    <Link
                      href={item.href}
                      aria-current={isActivePath(pathname, item.href) ? "page" : undefined}
                      onClick={() => setOpenMobile(false)}
                    >
                      <item.icon aria-hidden />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                  {item.badge === "pendingReviews" && pendingCount ? (
                    <SidebarMenuBadge
                      className="right-2 rounded-full bg-amber-500 px-1.5 text-[11px] font-bold text-slate-950"
                      aria-label={`${pendingCount} reviews pending`}
                    >
                      {pendingCount}
                    </SidebarMenuBadge>
                  ) : null}
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="shrink-0 gap-2 p-3 group-data-[collapsible=icon]:p-2">
        <ModeCard />
        <div className="border-t border-white/10 pt-2">
          {user ? (
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild size="lg" tooltip="User Profile" className="h-14 gap-3 rounded-lg px-2 hover:bg-white/5">
                  <Link
                    href="/settings#account"
                    aria-label={`User profile for ${user.name}`}
                    onClick={() => setOpenMobile(false)}
                  >
                    <span
                      className="flex size-10 shrink-0 items-center justify-center rounded-full bg-slate-700 text-sm font-semibold text-white group-data-[collapsible=icon]:size-8"
                      aria-hidden
                    >
                      {initials(user.name)}
                    </span>
                    <span className="min-w-0 group-data-[collapsible=icon]:hidden">
                      <span className="block truncate text-sm font-semibold text-white">{user.name}</span>
                      <span className="block truncate text-xs text-slate-400">{user.isDemo ? `${user.title} · Demo user` : user.title}</span>
                    </span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          ) : (
            <p className="pt-1 text-xs leading-relaxed text-slate-400 group-data-[collapsible=icon]:hidden">
              Not signed in. The backend has no authentication yet.
            </p>
          )}
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                tooltip="Sign Out"
                className={ITEM_CLASS}
                onClick={() => {
                  signOut();
                  setOpenMobile(false);
                  router.push("/login");
                }}
              >
                <LogOut aria-hidden />
                <span>Sign Out</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
