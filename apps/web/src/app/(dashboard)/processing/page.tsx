import type { Metadata } from "next";
import { ProcessingView } from "@/components/processing/processing-view";
import { OperationsGate } from "@/components/layout/operations-gate";

export const metadata: Metadata = { title: "Processing Activity" };

export default function ProcessingPage() {
  return <OperationsGate><ProcessingView /></OperationsGate>;
}
