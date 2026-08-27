'use client';

import PackingListDocumentsTab from '../../components/PackingListDocumentsTab';
import { PackingListRecordSkeleton } from '../components/packing-list-skeleton';
import { usePackingListRecord } from '../components/packing-list-context';

/** Every file this container is answered by. */
export default function PackingListDocumentsPage() {
  const { isLoading } = usePackingListRecord();
  if (isLoading) return <PackingListRecordSkeleton />;
  return <PackingListDocumentsTab />;
}
