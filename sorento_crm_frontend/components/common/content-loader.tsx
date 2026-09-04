import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * A content area waiting for its own data - a page layout gate (settings,
 * account), a detail page's own client fetch, an embedded iframe host
 * (M5-02). Generic because the caller's shape varies; a few `Skeleton` bars
 * read as "content is coming" without claiming a layout this component does
 * not own, the same reasoning `SectionSkeleton`'s doc comment gives.
 */
export function ContentLoader({ className }: { className?: string }) {
  return (
    <div className={cn('w-full max-w-md space-y-3', className)}>
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}
