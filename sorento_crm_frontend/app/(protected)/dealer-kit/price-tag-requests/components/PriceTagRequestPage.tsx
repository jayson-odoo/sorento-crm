'use client';

import { useRequestScope } from '@/hooks/useRequestScope';
import OwnPriceTagRequest from './OwnPriceTagRequest';
import PriceTagRequestDetail from './PriceTagRequestDetail';

/**
 * The request page: marketing's (`PriceTagRequestDetail`), or for a salesperson holding only
 * `view_own` their own request with the portal's actions (PORTAL-P4-REQUESTS S7).
 */
export default function PriceTagRequestPage({ requestId }: { requestId: string }) {
  const { limited } = useRequestScope('price_tag_request');
  return limited ? <OwnPriceTagRequest requestId={requestId} /> : <PriceTagRequestDetail requestId={requestId} />;
}
