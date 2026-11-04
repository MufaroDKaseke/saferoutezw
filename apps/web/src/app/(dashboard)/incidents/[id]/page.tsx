import type { Metadata } from "next";
import { IncidentDetail } from "@/components/incidents/incident-detail";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Incident" };

export default function IncidentDetailPage({ params }: PageProps<"/incidents/[id]">) {
  return <IdRoute params={params}>{(id) => <IncidentDetail id={id} />}</IdRoute>;
}
