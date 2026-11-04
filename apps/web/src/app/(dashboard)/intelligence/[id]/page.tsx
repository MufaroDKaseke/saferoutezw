import type { Metadata } from "next";
import { IntelligenceWorkspace } from "@/components/intelligence/intelligence-workspace";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Intelligence record" };

export default function IntelligenceDetailPage({ params }: PageProps<"/intelligence/[id]">) {
  return <IdRoute params={params}>{(id) => <IntelligenceWorkspace id={id} />}</IdRoute>;
}
