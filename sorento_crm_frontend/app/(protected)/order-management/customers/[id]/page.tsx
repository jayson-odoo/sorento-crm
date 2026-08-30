'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import CustomerDetail from '../components/CustomerDetail';

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Customer"
          actions={
            <BackToList
              listPath="/order-management/customers"
              label="Back to customers"
            />
          }
        />
      </Container>
      <Container>
        <CustomerDetail customerId={id} />
      </Container>
    </>
  );
}
