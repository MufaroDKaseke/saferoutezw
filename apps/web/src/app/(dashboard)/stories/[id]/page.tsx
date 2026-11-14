import type { Metadata } from "next";
import { StoryWorkspace } from "@/components/newsroom/story-workspace";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Story" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function StoryPage({ params }: PageProps<"/stories/[id]">) {
  return <IdRoute params={params}>{(id) => <StoryWorkspace id={id} />}</IdRoute>;
}
