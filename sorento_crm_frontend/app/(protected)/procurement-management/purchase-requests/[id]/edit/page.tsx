import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import PurchaseRequestForm from '../../components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'Edit Purchase Request',
  description: 'Edit purchase request or sponsorship form',
};

export default function EditPurchaseRequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <EditPurchaseRequestWrapper params={params} />
    </Container>
  );
}

async function EditPurchaseRequestWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <PageHeader
        title="Edit Purchase Request"
        actions={
          <Button variant="outline" asChild>
            <Link href={`/procurement-management/purchase-requests/${id}`}>
              Cancel
            </Link>
          </Button>
        }
      />
      <div className="mt-6">
        {/* A salesperson's own form reads ?from= / ?revise= (useSearchParams). */}
        <Suspense fallback={null}>
          <PurchaseRequestForm
            requestId={id}
            expectedRequestType="purchase_request"
            successRedirectUrl={`/procurement-management/purchase-requests/${id}`}
          />
        </Suspense>
      </div>
    </>
  );
}
