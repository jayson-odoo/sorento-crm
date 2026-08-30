'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SupplierForm from '../components/SupplierForm';

export default function NewSupplierPage() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Supplier"
          actions={
            <Button asChild variant="outline">
              <Link href="/procurement-management/suppliers">
                <MoveLeft /> Back to suppliers
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <SupplierForm
          onSuccess={() => {
            router.push('/procurement-management/suppliers');
          }}
        />
      </Container>
    </>
  );
}
