import type { Metadata } from "next";
import { Suspense } from "react";
import { MapView } from "@/components/public/map-view";
import { PageShell } from "@/components/public/site-chrome";
import { PageFallback } from "@/components/public/page-fallback";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: t("meta.map.title") };
}

async function MapContent() {
  const { t } = await getI18n();
  return (
    <PageShell title={t("map.title")} intro={t("map.intro")}>
      <MapView />
    </PageShell>
  );
}

export default function PublicMapPage() {
  return (
    <Suspense fallback={<PageFallback />}>
      <MapContent />
    </Suspense>
  );
}
