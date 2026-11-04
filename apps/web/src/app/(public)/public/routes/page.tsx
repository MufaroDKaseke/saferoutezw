import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingText } from "@/components/public/loading-text";
import { PageShell } from "@/components/public/site-chrome";
import { RoutePlanner } from "@/components/public/route-planner";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.routes.title") };
}

async function RoutesContent() {
  const { t } = await getI18n();
  return (
    <PageShell title={t("routes.title")} intro={t("routes.intro")}>
      <Suspense fallback={<LoadingText />}>
        <RoutePlanner />
      </Suspense>
    </PageShell>
  );
}

export default function RoutesPage() {
  return (
    <Suspense fallback={<PageFallback />}>
      <RoutesContent />
    </Suspense>
  );
}
