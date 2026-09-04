import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';
import { PageHeader } from '@/components/common/PageHeader';
import GRNList from './components/GRNList';

export const metadata: Metadata = {
  title: 'GRN',
  description: 'Manage Goods Receipt Notes',
};

export default function GRNPage() {
  return (
    <>
      <Container>
        <PageHeader title="Goods Receipt Notes" eyebrow="GRN" />
      </Container>

      <Container>
        <Suspense fallback={<ListPageSkeleton bodyOnly />}>
          <GRNList />
        </Suspense>
      </Container>
    </>
  );
}
