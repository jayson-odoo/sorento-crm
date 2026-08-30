import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import StockBalanceGrid from './components/StockBalanceGrid';

export const metadata: Metadata = {
  title: 'Stock',
  description: 'Manage stock inventory.',
};

export default function StockPage() {
  return (
    <>
      <Container>
        <PageHeader title="Stock" />
      </Container>

      <Container>
        <StockBalanceGrid />
      </Container>
    </>
  );
}
