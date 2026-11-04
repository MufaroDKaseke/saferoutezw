import type { Metadata } from "next";
import { IntelligenceList } from "@/components/intelligence/intelligence-list";

export const metadata: Metadata = { title: "Transport Intelligence" };

export default function IntelligencePage() {
  return <IntelligenceList />;
}
