'use client';

import BackToList from '@/components/common/BackToList';
import { PageHeader } from '@/components/common/PageHeader';
import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import { useRequestScope } from '@/hooks/useRequestScope';
import { PriceTagRequestForm } from '@/app/(auth)/portal/components/PriceTagRequestForm';
import PriceTagRequestDetail from './PriceTagRequestDetail';

/**
 * The request page: marketing's (`PriceTagRequestDetail`), or for a salesperson holding only
 * `view_own` their own request in the portal's own form (PORTAL-P4-REQUESTS R3, form parity).
 */
export default function PriceTagRequestPage({ requestId }: { requestId: string }) {
  const { limited } = useRequestScope('price_tag_request');
  return limited ? <PortalPriceTagRequest requestId={requestId} /> : <PriceTagRequestDetail requestId={requestId} />;
}

/**
 * A salesperson's own request (no `requestId`: a new one, `?from=<id>` read by the form itself):
 * the page's header and Back over the portal's form, through My Requests, with the D7 deletes.
 */
export function PortalPriceTagRequest({ requestId }: { requestId?: string }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title={requestId ? 'Price Tag Request' : 'New Price Tag Request'}
        actions={<BackToList listPath="/dealer-kit/price-tag-requests" label="Back to price tag requests" />}
      />
      <MyRequestClientProvider>
        <PriceTagRequestForm requestId={requestId} />
      </MyRequestClientProvider>
    </div>
  );
}
