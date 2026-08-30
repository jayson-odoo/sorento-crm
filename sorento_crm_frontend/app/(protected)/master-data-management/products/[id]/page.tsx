'use client';

import { use } from 'react';
import { useSearchParams } from 'next/navigation';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
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
  const worklistHref = worklistBackHref(searchParams.get('back'));

  return (
    <>
      <Container>
        <PageHeader
          title="Product"
          actions={worklistHref ? (
              <BackToList
                listPath={worklistHref}
                label="Back to spec verification"
                appendListState={false}
              />
            ) : (
              <BackToList
                listPath="/master-data-management/products"
                label="Back to products"
              />
            )}
        />
      </Container>

      <Container>
        <ProductDetail productId={id} />
      </Container>
    </>
  );
}
