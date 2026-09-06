import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';

/**
 * Held while this segment's chunk and first page arrive (M5-01 run 3).
 * `bodyOnly`: no `PageHeader` anywhere - `McpToolsList` puts its own
 * title in a `CardTitle`, so the default variant's title+crumb bar would
 * be for a heading that never lands (see `loading-inventory.test.tsx`'s
 * BODY_ONLY_SEGMENTS map).
 */
export default function Loading() {
  return <ListPageSkeleton bodyOnly />;
}
