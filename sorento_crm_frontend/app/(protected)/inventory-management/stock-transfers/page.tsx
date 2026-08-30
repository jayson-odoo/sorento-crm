import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { StockTransfersPanel } from './components/StockTransfersPanel';

export const metadata: Metadata = {
  title: 'Stock Transfers',
  description: 'Stock movements a confirmed supply decision has asked for.',
};

export default function StockTransfersPage() {
  return (
    <RequireAccess permission="inventory.stock_transfers.view">
      <Container className="space-y-6">
        <PageHeader title="Stock transfers" />

        <StockTransfersPanel listingKey="inventory.stock_transfers.view" />
      </Container>
    </RequireAccess>
  );
}
