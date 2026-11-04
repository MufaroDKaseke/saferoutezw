"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, Settings, User } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useDemoSession } from "@/hooks/use-demo-session";

export function UserMenu() {
  const router = useRouter();
  const { user, signOut } = useDemoSession();

  if (!user) {
    return (
      <Link href="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
        Sign in
      </Link>
    );
  }
  const initials = user.name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-3 rounded-lg p-1 pr-2 text-left outline-none hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-600"
        aria-label={`Account menu for ${user.name}`}
      >
        <Avatar className="size-10 bg-slate-900">
          <AvatarFallback className="bg-slate-900 text-sm font-semibold text-white">{initials}</AvatarFallback>
        </Avatar>
        <span className="hidden min-w-0 2xl:block">
          <span className="block truncate text-sm leading-tight font-semibold">{user.name}</span>
          <span className="block truncate text-xs text-slate-600">{user.title}</span>
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="space-y-0.5">
          <span className="block text-sm font-semibold text-foreground">{user.name}</span>
          <span className="block text-xs font-normal text-slate-600">{user.isDemo ? "Demo session · not real authentication" : user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings#account">
            <User aria-hidden /> User profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings aria-hidden /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            signOut();
            router.push("/login");
          }}
        >
          <LogOut aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
