import type { Metadata } from "next";
import { Suspense } from "react";
import { NewsMonitor } from "@/components/news/news-monitor";
import { NewsroomMonitor } from "@/components/newsroom/newsroom-monitor";
import { isNewsroomMode } from "@/lib/app-mode";
import { REGIONAL_LOCATION } from "@/lib/newsroom/taxonomy";
import { TableSkeleton } from "@/components/shared/states";

export const metadata: Metadata = { title: "News Monitor" };

async function NewsroomPage({ searchParams }: Pick<PageProps<"/news">, "searchParams">) {
  const query = await searchParams;
  const location = query.location === REGIONAL_LOCATION ? REGIONAL_LOCATION : undefined;
  return <NewsroomMonitor key={location ?? "all"} initialLocation={location} />;
}

export default function NewsPage({ searchParams }: PageProps<"/news">) {
  return isNewsroomMode ? (
    <Suspense fallback={<TableSkeleton rows={6} cols={4} />}>
      <NewsroomPage searchParams={searchParams} />
    </Suspense>
  ) : <NewsMonitor />;
}
