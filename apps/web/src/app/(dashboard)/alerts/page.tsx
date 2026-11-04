import type { Metadata } from "next";
import { AlertsView } from "@/components/alerts/alerts-view";

export const metadata: Metadata = { title: "Public Alerts" };

export default function AlertsPage() {
  return <AlertsView />;
}
