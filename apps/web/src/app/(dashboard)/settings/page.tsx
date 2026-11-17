import type { Metadata } from "next";
import { SettingsView } from "@/components/settings/settings-view";
import { OperationsGate } from "@/components/layout/operations-gate";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return <OperationsGate><SettingsView /></OperationsGate>;
}
