import type { Metadata } from "next";
import { MapView } from "@/components/public/map-view";
import { PageShell } from "@/components/public/site-chrome";

export const metadata: Metadata = { title: "Road safety map" };

export default function PublicMapPage() {
  return (
    <PageShell
      title="Road safety map"
      intro="Published road alerts with a reliable position. Historical blackspots are shown separately and describe past risk, not current alerts."
    >
      <MapView />
    </PageShell>
  );
}
