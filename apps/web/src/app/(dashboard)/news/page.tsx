import type { Metadata } from "next";
import { NewsMonitor } from "@/components/news/news-monitor";
import { NewsroomMonitor } from "@/components/newsroom/newsroom-monitor";
import { isNewsroomMode } from "@/lib/app-mode";

export const metadata: Metadata = { title: "News Monitor" };

export default function NewsPage() {
  return isNewsroomMode ? <NewsroomMonitor /> : <NewsMonitor />;
}
