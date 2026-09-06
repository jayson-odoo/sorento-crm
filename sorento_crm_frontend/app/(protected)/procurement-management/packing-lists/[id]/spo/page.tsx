'use client';

import { useSearchParams } from 'next/navigation';

import SpoPlannerTable from '../../components/SpoPlannerTable';
import { usePackingListRecord } from '../components/packing-list-context';

/** Turning what was packed into shipping orders against the open POs behind it. */
export default function PackingListSpoPage() {
  const { packingListId } = usePackingListRecord();
  const searchParams = useSearchParams();
  // `?edit=<purchase_order_id>` (R24, AC-K5) - the SPO document's own "Edit in planner"
  // action lands here, and the planner opens straight into edit mode for that SPO. Read
  // HERE rather than in the table so the table has no router dependency of its own.
  return (
    <SpoPlannerTable
      shipmentId={packingListId}
      initialEditPurchaseOrderId={searchParams.get('edit')}
    />
  );
}
