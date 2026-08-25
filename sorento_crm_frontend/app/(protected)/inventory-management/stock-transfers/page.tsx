import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
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
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Inventory</BreadcrumbPage>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Stock Transfers</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 break-words">
            <h1 className="text-xl font-semibold">Stock transfers</h1>
          </div>
        </header>

        <StockTransfersPanel listingKey="inventory.stock_transfers.view" />
      </Container>
    </RequireAccess>
  );
}
