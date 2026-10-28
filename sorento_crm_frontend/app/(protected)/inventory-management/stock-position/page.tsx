import { Metadata } from 'next';
import { Container } from '@/components/common/container';
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
        <StockPositionGrid />
      </Container>
    </>
  );
}
