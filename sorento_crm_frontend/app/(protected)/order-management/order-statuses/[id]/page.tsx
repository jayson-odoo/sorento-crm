'use client';

import { use } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderStatusDetail from '../components/OrderStatusDetail';

export default function OrderStatusDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Delivery Order Status"
          actions={
            <Button asChild variant="outline">
              <Link href="/order-management/order-statuses">
                <MoveLeft /> Back to delivery order statuses
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <OrderStatusDetail orderStatusId={id} />
      </Container>
    </>
  );
}
