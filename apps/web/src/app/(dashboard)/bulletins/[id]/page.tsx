import type { Metadata } from "next";
import { BulletinBuilder } from "@/components/newsroom/bulletin-builder";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Bulletin" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function BulletinPage({ params }: PageProps<"/bulletins/[id]">) {
  return <IdRoute params={params}>{(id) => <BulletinBuilder id={id} />}</IdRoute>;
}
