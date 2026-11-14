import type { Metadata } from "next";
import { ArticleDetail } from "@/components/news/article-detail";
import { NewsroomArticleDetail } from "@/components/newsroom/newsroom-article-detail";
import { IdRoute } from "@/components/shared/id-route";
import { isNewsroomMode } from "@/lib/app-mode";

export const metadata: Metadata = { title: "Article" };

export default function NewsDetailPage({ params }: PageProps<"/news/[id]">) {
  return (
    <IdRoute params={params}>
      {(id) => (isNewsroomMode ? <NewsroomArticleDetail id={id} /> : <ArticleDetail id={id} />)}
    </IdRoute>
  );
}
