import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SPOAllocationsList from './components/SPOAllocationsList';

export const metadata: Metadata = {
  title: 'SPO Allocations',
  description: 'Manage Stock Purchase Order allocations',
};

export default function SPOAllocationsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Supplier PO Allocations" eyebrow="SPO" />
      </Container>

      <Container>
        <Suspense fallback={<div>Loading...</div>}>
          <SPOAllocationsList />
        </Suspense>
      </Container>
    </>
  );
}
