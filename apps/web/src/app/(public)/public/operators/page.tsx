import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingText } from "@/components/public/loading-text";
import { PageShell } from "@/components/public/site-chrome";
import { RoutePlanner } from "@/components/public/route-planner";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.operators.title") };
}

async function OperatorsContent() {
  const { t } = await getI18n();
  return (
    <PageShell title={t("operators.title")} intro={t("operators.intro")}>
      <Suspense fallback={<LoadingText />}>
        <RoutePlanner operator />
      </Suspense>
    </PageShell>
  );
}

export default function OperatorsPage() {
  return (
    <Suspense fallback={<PageFallback />}>
      <OperatorsContent />
    </Suspense>
  );
}
