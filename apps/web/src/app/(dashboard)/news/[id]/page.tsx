import type { Metadata } from "next";
import { ArticleDetail } from "@/components/news/article-detail";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Article" };

export default function NewsDetailPage({ params }: PageProps<"/news/[id]">) {
  return <IdRoute params={params}>{(id) => <ArticleDetail id={id} />}</IdRoute>;
}
