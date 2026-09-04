import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';
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
        <PageHeader title="SPO Allocations" />
      </Container>

      <Container>
        <Suspense fallback={<ListPageSkeleton bodyOnly />}>
          <SPOAllocationsList />
        </Suspense>
      </Container>
    </>
  );
}
