import type { Metadata } from "next";
import { StudioIndex } from "@/components/newsroom/studio-index";

export const metadata: Metadata = { title: "Studio" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function StudioPage() {
  return <StudioIndex />;
}
