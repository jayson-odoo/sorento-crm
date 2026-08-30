import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PurchaseRequestsList from './components/PurchaseRequestsList';

export const metadata: Metadata = {
  title: 'Purchase Requests',
  description: 'Purchase requests and sponsorship forms',
};

export default function PurchaseRequestsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Purchase Requests" />
      </Container>

      <Container>
        <PurchaseRequestsList
          requestType="purchase_request"
          basePath="/procurement-management/purchase-requests"
        />
      </Container>
    </>
  );
}
