"use client";

import type { Resource } from "@/hooks/use-resource";
import { CardBodySkeleton, QueryError } from "./states";

/**
 * One place for the loading / error / not-available branches, so every page
 * handles them the same way. `children` only renders with real data.
 */
export function ResourceView<T>({
  resource,
  skeleton,
  what,
  children,
}: {
  resource: Resource<T>;
  skeleton?: React.ReactNode;
  what?: string;
  children: (data: T) => React.ReactNode;
}) {
  if (resource.error) {
    return <QueryError error={resource.error} onRetry={resource.refetch} what={what} />;
  }
  if (resource.data === undefined) {
    return <>{skeleton ?? <CardBodySkeleton />}</>;
  }
  return <>{children(resource.data)}</>;
}
