import type { Metadata } from "next";
import { ManageSubscription } from "@/components/public/manage-subscription";
import { PageShell } from "@/components/public/site-chrome";

export const metadata: Metadata = { title: "Manage alerts" };

export default function ManageSubscriptionPage() {
  return (
    <PageShell title="Manage your alerts" intro="Confirm your number to change your areas or unsubscribe.">
      <ManageSubscription />
    </PageShell>
  );
}
