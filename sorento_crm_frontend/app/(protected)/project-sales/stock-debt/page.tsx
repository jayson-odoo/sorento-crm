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
      <Container className="space-y-6">
        {/* The sidebar names this page (Project Sales > Project Demand > Stock Debt),
            so the trail derives itself from the pathname - no `crumbs` override, the
            way its Fulfilment Planning and Plans siblings do it (S5-01, S5-02). */}
        <PageHeader title="Stock debt" />
        <StockDebtClient />
      </Container>
    </RequireAccess>
  );
}
