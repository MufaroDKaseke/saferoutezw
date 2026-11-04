import type { Metadata } from "next";
import { AlertDetail } from "@/components/alerts/alert-detail";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Alert" };

export default function AlertDetailPage({ params }: PageProps<"/alerts/[id]">) {
  return <IdRoute params={params}>{(id) => <AlertDetail id={id} />}</IdRoute>;
}
