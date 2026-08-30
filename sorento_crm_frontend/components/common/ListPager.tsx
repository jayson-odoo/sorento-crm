'use client';

import RecordNavigation from './RecordNavigation';
import { useListPager, type UseListPagerOptions } from '@/hooks/useListPager';

export interface ListPagerProps extends UseListPagerOptions {
  /** e.g. "delivery order" - used for the chevrons' accessible names. */
  ariaLabel?: string;
  className?: string;
}

/**
 * Prev/next across the list page the user came from (S3-03, S3-04).
 *
 * Renders nothing when the record is not on that page (deep link into a set it
 * does not belong to, or the row was deleted) - see `useListPager` for the
 * hook/data contract an entity has to satisfy.
 */
export default function ListPager({ ariaLabel, className, ...options }: ListPagerProps) {
  const pager = useListPager(options);

  if (!pager.visible) return null;

  return (
    <RecordNavigation
      index={pager.index}
      total={pager.total}
      hasPrevious={pager.hasPrevious}
      hasNext={pager.hasNext}
      onPrevious={pager.goPrevious}
      onNext={pager.goNext}
      isLoading={pager.isLoading}
      ariaLabel={ariaLabel}
      className={className}
    />
  );
}
