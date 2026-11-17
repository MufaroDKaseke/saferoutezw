"use client";

import { useSession } from "@/hooks/use-demo-session";
import { getDataMode } from "@/lib/api/config";
import { roleTitle } from "@/lib/newsroom/roles";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, EmptyState } from "@/components/shared/states";
import { ChangePassword } from "./change-password";

export function AccountView() {
  const { user, loading } = useSession();
  if (loading) return <CardBodySkeleton lines={5} />;
  if (!user) return <EmptyState title="Sign in to view your account" />;
  return (
    <div className="space-y-6">
      <PageHeader title="Your account" description="Your profile and sign-in password." />
      <SectionCard id="profile" title="Profile">
        <dl className="space-y-4 text-sm">
          <div><dt className="text-xs text-slate-600">Name</dt><dd className="mt-1 font-semibold">{user.name}</dd></div>
          <div><dt className="text-xs text-slate-600">Email</dt><dd className="mt-1">{user.email}</dd></div>
          <div><dt className="text-xs text-slate-600">Role</dt><dd className="mt-1">{roleTitle(user.role)}</dd></div>
        </dl>
      </SectionCard>
      <SectionCard id="password" className="scroll-mt-24" title="Change password" description="Choose a new password for your account.">
        {!user.isDemo && getDataMode() === "api" ? <ChangePassword /> : <p className="text-sm text-slate-600">Password changes are available for live accounts.</p>}
      </SectionCard>
    </div>
  );
}
