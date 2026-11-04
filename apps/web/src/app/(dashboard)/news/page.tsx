import type { Metadata } from "next";
import { NewsMonitor } from "@/components/news/news-monitor";

export const metadata: Metadata = { title: "News Monitor" };

export default function NewsPage() {
  return <NewsMonitor />;
}
