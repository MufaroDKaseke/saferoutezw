import type { Metadata } from "next";
import { ArchiveView } from "@/components/newsroom/archive-view";

export const metadata: Metadata = { title: "Archive" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function ArchivePage() {
  return <ArchiveView />;
}
