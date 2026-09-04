import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

export interface SectionSkeletonProps {
  /** How many bars to draw. Three reads as "a short list of rows is coming". */
  rows?: number;
  className?: string;
}

/**
 * What a card body, dialog panel, tab body, sidebar list or widget shows
 * while ITS OWN data is in flight (M5-02) - a few `Skeleton` bars, the
 * sibling of `ListPageSkeleton` for content that is not a full DataGrid
 * page. A spinner plus a status word reads as "wait, no shape yet"; bars in
 * the section's own wrapper read as "this is roughly what's coming",
 * which is the same reasoning `ListPageSkeleton`'s doc comment gives for a
 * whole list route.
 *
 * Deliberately generic, same reason `ListPageSkeleton` is: a bar per section
 * is a fair stand-in for a paragraph, a short list or a form's fields alike,
 * without becoming a second copy of each caller's real layout.
 */
export function SectionSkeleton({ rows = 3, className }: SectionSkeletonProps) {
  return (
    <div className={cn('space-y-2', className)} data-slot="section-skeleton">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  );
}
