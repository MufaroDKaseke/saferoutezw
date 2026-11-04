import type { Metadata } from "next";
import { BlackspotsView } from "@/components/blackspots/blackspots-view";

export const metadata: Metadata = { title: "Historical Blackspots" };

export default function BlackspotsPage() {
  return <BlackspotsView />;
}
