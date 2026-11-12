import type { Metadata } from "next";
import { ArchiveStoryView } from "@/components/newsroom/archive-story";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Archived story" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function ArchivedStoryPage({ params }: PageProps<"/archive/stories/[id]">) {
  return <IdRoute params={params}>{(id) => <ArchiveStoryView id={id} />}</IdRoute>;
}
