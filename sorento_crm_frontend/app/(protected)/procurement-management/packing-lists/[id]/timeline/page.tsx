'use client';

import PackingListTimelineTab from '../../components/PackingListTimelineTab';
import { PackingListRecordSkeleton } from '../components/packing-list-skeleton';
import { usePackingListRecord } from '../components/packing-list-context';

/** How far the container has got, checkpoint by checkpoint. */
export default function PackingListTimelinePage() {
  const { isLoading } = usePackingListRecord();
  if (isLoading) return <PackingListRecordSkeleton />;
  return <PackingListTimelineTab />;
}
