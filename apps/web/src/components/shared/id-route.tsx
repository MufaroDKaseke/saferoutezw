import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * With Cache Components, reading route `params` is request-time data and must
 * sit inside a <Suspense> boundary. This wrapper keeps that rule in one place:
 * the page renders instantly with a skeleton, then the client view mounts with
 * the id.
 */
export function IdRoute({
  params,
  children,
}: {
  params: Promise<{ id: string }>;
  children: (id: string) => React.ReactNode;
}) {
  return (
    <Suspense fallback={<DetailFallback />}>
      <Resolved params={params} render={children} />
    </Suspense>
  );
}

async function Resolved({
  params,
  render,
}: {
  params: Promise<{ id: string }>;
  render: (id: string) => React.ReactNode;
}) {
  const { id } = await params;
  return <>{render(decodeURIComponent(id))}</>;
}

function DetailFallback() {
  return (
    <div className="space-y-6" aria-busy="true">
      <span role="status" className="sr-only">
        Loading…
      </span>
      <div className="space-y-3">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-96 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    </div>
  );
}
