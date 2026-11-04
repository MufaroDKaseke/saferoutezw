import type { Metadata } from "next";
import { ReviewQueue } from "@/components/editorial/review-queue";

export const metadata: Metadata = { title: "Review Queue" };

export default function ReviewsPage() {
  return <ReviewQueue />;
}
