import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { StockDebtClient } from './components/StockDebtClient';

export const metadata: Metadata = {
  title: 'Stock Debt',
  description:
    'Every outstanding sales order without supply, as a running balance per product and month.',
};

export default function StockDebtPage() {
  return (
    <RequireAccess permission="projects.stock_debt.view">
      <Container>
        <PageHeader title="Stock Debt" />
      </Container>

      <Container>
        <StockDebtClient />
      </Container>
    </RequireAccess>
  );
}
