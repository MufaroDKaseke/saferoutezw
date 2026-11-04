import type { Metadata } from "next";
import { ReviewWorkspaceView } from "@/components/editorial/review-workspace";
import { IdRoute } from "@/components/shared/id-route";

export const metadata: Metadata = { title: "Review" };

export default function ReviewDetailPage({ params }: PageProps<"/reviews/[id]">) {
  return <IdRoute params={params}>{(id) => <ReviewWorkspaceView id={id} />}</IdRoute>;
}
