'use client';

import SourceProformaInvoicesCard from '../../components/SourceProformaInvoicesCard';
import { PackingListRecordSkeleton } from '../components/packing-list-skeleton';
import { usePackingListRecord } from '../components/packing-list-context';

/**
 * Which proforma invoices this container was drafted from, and how much of each came here.
 *
 * A tab of its own rather than the one-line "Origin" card it replaces: one invoice may be
 * split across two containers, so "200 of 500 came here" is a table's worth of answer and
 * a sentence could only ever give half of it.
 */
export default function PackingListProformaInvoicesPage() {
  const { packingListId, packingList, isLoading } = usePackingListRecord();
  if (isLoading) return <PackingListRecordSkeleton />;
  return (
    <SourceProformaInvoicesCard
      packingListId={packingListId}
      convertedOn={packingList?.created_at ?? null}
    />
  );
}
