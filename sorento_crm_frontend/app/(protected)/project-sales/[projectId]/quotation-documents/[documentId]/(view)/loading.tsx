import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';

/**
 * Held while the Header tab's chunk and first page arrive (M5-01). The Header tab carries the
 * lines grid (PROPOSAL-HEADER-LAYOUT). `bodyOnly`: the parent (view)/layout.tsx already renders
 * the page header - see `loading-inventory.test.tsx`'s BODY_ONLY_SEGMENTS map.
 */
export default function Loading() {
  return <ListPageSkeleton bodyOnly />;
}
