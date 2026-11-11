import type { Metadata } from "next";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { NewsroomDashboard } from "@/components/newsroom/newsroom-dashboard";
import { isNewsroomMode } from "@/lib/app-mode";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return isNewsroomMode ? <NewsroomDashboard /> : <DashboardView />;
}
