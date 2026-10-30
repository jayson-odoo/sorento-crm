'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductForm from '../components/ProductForm';
import RequireAccess from '@/app/components/common/RequireAccess';

export default function NewProductPage() {
  return (
    <RequireAccess permission="master_data.products.add">
      <NewProductPageBody />
    </RequireAccess>
  );
}

function NewProductPageBody() {
  const router = useRouter();

  return (
    <>
      <Container>
        <PageHeader
          title="Create Product"
          actions={
            <Button asChild variant="outline">
              <Link href="/master-data-management/products">
                <MoveLeft /> Back to products
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <ProductForm
          productId={undefined}
          onSuccess={() => {
            router.push('/master-data-management/products');
          }}
        />
      </Container>
    </>
  );
}
