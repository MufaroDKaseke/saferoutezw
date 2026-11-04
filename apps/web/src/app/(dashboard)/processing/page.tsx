import type { Metadata } from "next";
import { ProcessingView } from "@/components/processing/processing-view";

export const metadata: Metadata = { title: "Processing Activity" };

export default function ProcessingPage() {
  return <ProcessingView />;
}
