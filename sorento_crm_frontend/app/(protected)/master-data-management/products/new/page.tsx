'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductForm from '../components/ProductForm';

export default function NewProductPage() {
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
