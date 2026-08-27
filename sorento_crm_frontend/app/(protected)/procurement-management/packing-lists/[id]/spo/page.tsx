'use client';

import SpoPlannerTable from '../../components/SpoPlannerTable';
import { usePackingListRecord } from '../components/packing-list-context';

/** Turning what was packed into shipping orders against the open POs behind it. */
export default function PackingListSpoPage() {
  const { packingListId } = usePackingListRecord();
  return <SpoPlannerTable shipmentId={packingListId} />;
}
