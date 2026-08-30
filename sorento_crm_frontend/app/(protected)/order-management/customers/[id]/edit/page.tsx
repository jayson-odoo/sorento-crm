'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CustomerForm from '../../components/CustomerForm';

export default function EditCustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Customer"
          actions={
            <Button asChild variant="outline">
              <Link href={`/order-management/customers/${id}`}>
                <MoveLeft /> Back to customer
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <CustomerForm
          customerId={id}
          onSuccess={() => {
            router.push(`/order-management/customers/${id}`);
          }}
        />
      </Container>
    </>
  );
}
