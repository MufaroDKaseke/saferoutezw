"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useBreadcrumbLabel } from "./breadcrumb-label";
import { GlobalSearch } from "./global-search";
import { isNewsroomMode } from "@/lib/app-mode";
import { NewsroomSearch } from "@/components/newsroom/newsroom-search";
import { SECTION_BY_SEGMENT } from "./nav-config";
import { NotificationsMenu } from "./notifications-menu";
import { SystemStatus } from "./system-status";
import { UserMenu } from "./user-menu";

function Crumbs() {
  const pathname = usePathname();
  const label = useBreadcrumbLabel(pathname);
  const [first, second] = pathname.split("/").filter(Boolean);
  const section = first ? SECTION_BY_SEGMENT[first] : undefined;

  const crumbs: { text: string; href?: string }[] = [];
  if (section) {
    crumbs.push({ text: section.group });
    crumbs.push({ text: section.title, href: second ? section.href : undefined });
    if (second) crumbs.push({ text: label ?? decodeURIComponent(second) });
  }

  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <Fragment key={`${crumb.text}-${index}`}>
              <BreadcrumbItem className={last ? "min-w-0" : "hidden sm:inline-flex"}>
                {last ? (
                  <BreadcrumbPage className="truncate font-semibold text-foreground">{crumb.text}</BreadcrumbPage>
                ) : crumb.href ? (
                  <BreadcrumbLink asChild>
                    <Link href={crumb.href}>{crumb.text}</Link>
                  </BreadcrumbLink>
                ) : (
                  <span className="text-slate-600">{crumb.text}</span>
                )}
              </BreadcrumbItem>
              {!last ? <BreadcrumbSeparator className="hidden sm:flex" /> : null}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function AppHeader() {
  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card/95 px-4 py-2.5 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <SidebarTrigger className="size-10 shrink-0" />
        <Crumbs />
      </div>
      <div className="order-last basis-full md:order-none md:basis-auto">
        {isNewsroomMode ? <NewsroomSearch /> : <GlobalSearch />}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <div className="hidden xl:block">
          <SystemStatus />
        </div>
        {isNewsroomMode ? null : <NotificationsMenu />}
        <UserMenu />
      </div>
    </header>
  );
}
