"use client";

import Link from "next/link";
import { useSession } from "@/hooks/use-demo-session";
import { canAccessOperations } from "@/lib/newsroom/roles";
import { EmptyState, TableSkeleton } from "@/components/shared/states";

/** Gate the view itself so direct links cannot mount operational data loaders. */
export function OperationsGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession();
  if (canAccessOperations(user?.role)) return <>{children}</>;
  if (loading) return <TableSkeleton rows={5} cols={4} />;
  return <EmptyState title="Administrator access required" description="Operations pages are available to Administrators."
    action={<Link href="/dashboard" className="font-semibold text-brand-blue hover:underline">Return to dashboard</Link>} />;
}
