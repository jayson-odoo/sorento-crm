'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import ClearanceDeliveryCard from './ClearanceDeliveryCard';
import { usePackingListRecord } from '../[id]/components/packing-list-context';

/**
 * How far the container has got, checkpoint by checkpoint.
 *
 * The "Origin" card that used to sit above this is gone: where a container came from is a
 * whole tab of its own now (Proforma invoices), and a one-line summary of it here was the
 * only place on the page that answered the question in a sentence rather than in figures.
 */
export function PackingListTimelineTab() {
  const { packingList } = usePackingListRecord();
  if (!packingList) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Clearance &amp; Delivery</CardTitle>
      </CardHeader>
      <CardContent>
        <ClearanceDeliveryCard packingList={packingList} />
      </CardContent>
    </Card>
  );
}

export default PackingListTimelineTab;
