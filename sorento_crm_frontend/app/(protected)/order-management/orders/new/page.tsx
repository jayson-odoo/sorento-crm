'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderForm from '../components/OrderForm';

export default function NewOrderPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Delivery Order"
          actions={
            <Button asChild variant="outline">
              <Link href="/order-management/orders">
                <MoveLeft /> Back to delivery orders
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <OrderForm
          onSuccess={() => {
            router.push('/order-management/orders');
          }}
        />
      </Container>
    </>
  );
}
