'use client';

import PackingListDetailsTab from '../components/PackingListDetailsTab';
import { PackingListRecordSkeleton } from './components/packing-list-skeleton';
import { usePackingListRecord } from './components/packing-list-context';

/** Details: what the container is, what it costs to land, and how far it has cleared. */
export default function PackingListDetailsPage() {
  const { isLoading, packingList } = usePackingListRecord();
  if (isLoading) return <PackingListRecordSkeleton />;
  if (!packingList) return <PackingListNotFound />;
  return <PackingListDetailsTab />;
}

function PackingListNotFound() {
  return (
    <p className="py-12 text-center text-sm text-muted-foreground">
      Packing list not found.
    </p>
  );
}
