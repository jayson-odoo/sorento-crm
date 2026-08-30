'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import SupplierDetail from './components/SupplierDetail';

export default function SupplierDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Supplier"
          actions={
            <BackToList
              listPath="/procurement-management/suppliers"
              label="Back to suppliers"
            />
          }
        />
      </Container>

      <Container>
        <SupplierDetail supplierId={id} />
      </Container>
    </>
  );
}
