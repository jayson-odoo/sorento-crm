import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { StockTransferDetail } from './components/StockTransferDetail';

export const metadata: Metadata = {
  title: 'Stock Transfer',
  description: 'One stock movement, and what has been done about it.',
};

export default async function StockTransferDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // The breadcrumb lives INSIDE the detail component, not here: its leaf is the transfer
  // NUMBER, and this server component holds only the id - which is a UUID and may never
  // reach a screen.
  return (
    <RequireAccess permission="inventory.stock_transfers.view">
      <Container className="space-y-6">
        <StockTransferDetail id={id} />
      </Container>
    </RequireAccess>
  );
}
