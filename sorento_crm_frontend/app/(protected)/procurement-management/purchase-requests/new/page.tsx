import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import PurchaseRequestForm from '../components/PurchaseRequestForm';

export const metadata: Metadata = {
  title: 'New Purchase Request',
  description: 'Create a purchase request or sponsorship form',
};

export default function NewPurchaseRequestPage() {
  return (
    <Container>
      <PageHeader
        title="New Purchase Request"
        actions={
          <Button variant="outline" asChild>
            <Link href="/procurement-management/purchase-requests">Cancel</Link>
          </Button>
        }
      />
      <div className="mt-6">
        {/* A salesperson's own form reads ?from= / ?revise= (useSearchParams). */}
        <Suspense fallback={null}>
          <PurchaseRequestForm
            successRedirectUrl="/procurement-management/purchase-requests"
          />
        </Suspense>
      </div>
    </Container>
  );
}
