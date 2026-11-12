import type { Metadata } from "next";
import { StudioScreen } from "@/components/newsroom/studio-screen";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Studio" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function StudioBulletinPage({ params }: PageProps<"/studio/[id]">) {
  return <IdRoute params={params}>{(id) => <StudioScreen id={id} />}</IdRoute>;
}
