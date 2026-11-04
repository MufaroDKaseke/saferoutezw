import type { Metadata } from "next";
import { StatisticsView } from "@/components/intelligence/statistics-view";

export const metadata: Metadata = { title: "Statistics and trends" };

export default function StatisticsPage() {
  return <StatisticsView />;
}
