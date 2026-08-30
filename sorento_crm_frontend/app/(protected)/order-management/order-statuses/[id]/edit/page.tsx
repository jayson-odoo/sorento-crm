'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderStatusForm from '../../components/OrderStatusForm';

export default function EditOrderStatusPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Delivery Order Status"
          actions={
            <Button asChild variant="outline">
              <Link href={`/order-management/order-statuses/${id}`}>
                <MoveLeft /> Back to delivery order status
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <OrderStatusForm
          orderStatusId={id}
          onSuccess={() => {
            router.push(`/order-management/order-statuses/${id}`);
          }}
        />
      </Container>
    </>
  );
}
