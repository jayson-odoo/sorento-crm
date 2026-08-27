'use client';

import { Skeleton } from '@/components/ui/skeleton';

/** One loading shape for every tab, so switching between them does not change height. */
export function PackingListRecordSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

export default PackingListRecordSkeleton;
