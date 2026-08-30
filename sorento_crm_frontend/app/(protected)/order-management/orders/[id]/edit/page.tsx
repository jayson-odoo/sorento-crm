'use client';

import { use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderForm from '../../components/OrderForm';

export default function EditOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const listQs = searchParams.toString();
  const detailHref = listQs ? `/order-management/orders/${id}?${listQs}` : `/order-management/orders/${id}`;

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Delivery Order"
          actions={
            <Button asChild variant="outline">
              <Link href={detailHref}>
                <MoveLeft /> Back to delivery order
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <OrderForm
          orderId={id}
          onSuccess={() => {
            router.push(detailHref);
          }}
        />
      </Container>
    </>
  );
}
