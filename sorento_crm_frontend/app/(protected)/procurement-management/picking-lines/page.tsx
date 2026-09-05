import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';
import { PageHeader } from '@/components/common/PageHeader';
import PickingLinesList from './components/PickingLinesList';

export const metadata: Metadata = {
  title: 'Picking Lines',
  description: 'View GRN picking lines with location, expected and picked quantities',
};

export default function PickingLinesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Picking Lines" />
      </Container>

      <Container>
        <Suspense fallback={<ListPageSkeleton bodyOnly />}>
          <PickingLinesList />
        </Suspense>
      </Container>
    </>
  );
}
