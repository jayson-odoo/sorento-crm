'use client';

import { use } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
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
import ProductDetail from './components/ProductDetail';

const WORKLIST_PATH = '/master-data-management/spec-verification';

/**
 * Where Back goes when the user did not come from the products list.
 *
 * The spec verification worklist hands its whole URL over in `back` (search, filters,
 * sort, page, selection and the row being left), because a reviewer who opened a
 * product to check one value must land back on that list exactly as they left it, not
 * on a fresh products list (captain ruling 2026-08-17). Anything that is not a relative
 * path into that worklist is ignored - a `back` pointing anywhere else would be an open
 * redirect wearing a Back button.
 */
function worklistBackHref(raw: string | null): string | null {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return null;
  return raw.split('?')[0] === WORKLIST_PATH ? raw : null;
}

export default function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const listQueryString = searchParams.toString();
  const worklistHref = worklistBackHref(searchParams.get('back'));
  const backHref =
    worklistHref ??
    (listQueryString
      ? `/master-data-management/products?${listQueryString}`
      : '/master-data-management/products');
  const backLabel = worklistHref
    ? 'Back to spec verification'
    : 'Back to products';

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Product</ToolbarTitle>
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
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href={backHref}>
                <MoveLeft /> {backLabel}
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <ProductDetail productId={id} />
      </Container>
    </>
  );
}
