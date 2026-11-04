import type { Metadata } from "next";
import { PageShell } from "@/components/public/site-chrome";
import { SubscribeForm } from "@/components/public/subscribe-form";

export const metadata: Metadata = { title: "Get road alerts" };

export default function SubscribePage() {
  return (
    <PageShell
      title="Get road alerts by SMS or WhatsApp"
      intro="No account needed. We verify your number first and only send alerts that editors have reviewed and published."
    >
      <SubscribeForm />
    </PageShell>
  );
}
