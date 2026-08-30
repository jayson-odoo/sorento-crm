'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CustomerForm from '../components/CustomerForm';

export default function NewCustomerPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Customer"
          actions={
            <Button asChild variant="outline">
              <Link href="/order-management/customers">
                <MoveLeft /> Back to customers
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <CustomerForm
          onSuccess={() => {
            router.push('/order-management/customers');
          }}
        />
      </Container>
    </>
  );
}
