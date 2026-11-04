import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { ListPageSkeleton } from '@/components/common/ListPageSkeleton';
import { PageHeader } from '@/components/common/PageHeader';
import StockPositionGrid from './components/StockPositionGrid';

export const metadata: Metadata = {
  title: 'Stock position',
  description: 'Stock, incoming, outstanding and sales per item, every supplier.',
};

export default function StockPositionPage() {
  return (
    <>
      <Container>
        <PageHeader title="Stock position" />
      </Container>
      <Container>
        {/* The grid reads its filters, sort and page from the URL (useSearchParams). */}
        <Suspense fallback={<ListPageSkeleton bodyOnly />}>
          <StockPositionGrid />
        </Suspense>
      </Container>
    </>
  );
}
