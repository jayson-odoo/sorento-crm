'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderStatusForm from '../components/OrderStatusForm';

export default function NewOrderStatusPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Delivery Order Status"
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
        <OrderStatusForm
          onSuccess={() => {
            router.push('/order-management/order-statuses');
          }}
        />
      </Container>
    </>
  );
}
