import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';

/**
 * Held while this segment's chunk arrives (M5-01 run 3). `bodyOnly`:
 * `user-management/settings/layout.tsx` already renders the `PageHeader`
 * ("Settings") for every settings page, the same reason
 * `settings/portal-revisions` is `bodyOnly` - see `loading-inventory.test.tsx`'s
 * BODY_ONLY_SEGMENTS map.
 */
export default function Loading() {
  return <ListPageSkeleton bodyOnly />;
}
