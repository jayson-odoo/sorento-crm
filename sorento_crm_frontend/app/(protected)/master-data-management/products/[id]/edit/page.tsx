'use client';

import { use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { LoaderCircleIcon, MoveLeft } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
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
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Edit Product</ToolbarTitle>
            </ToolbarHeading>
          </Toolbar>
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
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Edit Product</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Product Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/master-data-management/products">
                    Products
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href={`/master-data-management/products/${id}${querySuffix}`}>
                    Product
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href={`/master-data-management/products/${id}${querySuffix}`}>
                <MoveLeft /> Back to product
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
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
