import type { Metadata } from "next";
import { Suspense } from "react";
import { ManageSubscription } from "@/components/public/manage-subscription";
import { PageShell } from "@/components/public/site-chrome";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.manage.title") };
}

async function ManageContent() {
  const { t } = await getI18n();
  return (
    <PageShell title={t("manage.title")} intro={t("manage.intro")}>
      <ManageSubscription />
    </PageShell>
  );
}

export default function ManageSubscriptionPage() {
  return (
    <Suspense fallback={<PageFallback />}>
      <ManageContent />
    </Suspense>
  );
}
