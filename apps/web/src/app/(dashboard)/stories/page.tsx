import type { Metadata } from "next";
import { StoryBoard } from "@/components/newsroom/story-board";

export const metadata: Metadata = { title: "Stories" };

// NUST FM only: the proxy answers "not found" for this route in road-safety mode.
export default function StoriesPage() {
  return <StoryBoard />;
}
