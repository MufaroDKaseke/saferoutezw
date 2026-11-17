import type { Metadata } from "next";
import { SourcesView } from "@/components/sources/sources-view";
import { OperationsGate } from "@/components/layout/operations-gate";

export const metadata: Metadata = { title: "Data Sources" };

export default function SourcesPage() {
  return <OperationsGate><SourcesView /></OperationsGate>;
}
