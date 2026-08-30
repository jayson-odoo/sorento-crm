'use client';

import { use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { LoaderCircleIcon, MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductForm from '../../components/ProductForm';
import { useProduct } from '../../hooks/useProducts';

export default function EditProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: product } = useProduct(id);
  const qs = searchParams.toString();
  const querySuffix = qs ? `?${qs}` : '';

  // Wait for product only. Category, Brand, UOM are fetched inside ProductForm and use
  // product.category / product.brand / product.base_uom as display fallback (same pattern as UOM).
  if (product == null) {
    return (
      <>
        <Container>
          <PageHeader title="Edit Product" />
        </Container>
        <Container>
          <div className="flex items-center justify-center p-12">
            <LoaderCircleIcon className="size-8 animate-spin text-muted-foreground" />
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Container>
        <PageHeader
          title="Edit Product"
          actions={
            <Button asChild variant="outline">
              <Link href={`/master-data-management/products/${id}${querySuffix}`}>
                <MoveLeft /> Back to product
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <ProductForm
          key={id}
          productId={id}
          initialProduct={product}
          onSuccess={() => {
            router.push(`/master-data-management/products/${id}${querySuffix}`);
          }}
        />
      </Container>
    </>
  );
}
