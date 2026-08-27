'use client';

import PackingListLinesTab from '../../components/PackingListLinesTab';
import { PackingListRecordSkeleton } from '../components/packing-list-skeleton';
import { usePackingListRecord } from '../components/packing-list-context';

/** What is in the container, and what the workbook measures it by. */
export default function PackingListLinesPage() {
  const { isLoading } = usePackingListRecord();
  if (isLoading) return <PackingListRecordSkeleton />;
  return <PackingListLinesTab />;
}
