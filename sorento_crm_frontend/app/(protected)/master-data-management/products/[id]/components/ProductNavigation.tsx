'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useProductNeighbours } from '../../hooks/useProducts';

interface ProductNavigationProps {
  productId: string;
  className?: string;
}

export default function ProductNavigation({
  productId,
  className,
}: ProductNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      category_id: parsed.filters.category_id,
      brand_id: parsed.filters.brand_id,
      status: parsed.filters.status,
      discontinued_batch_id: parsed.filters.discontinued_batch_id,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useProductNeighbours(
    productId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(
      `/master-data-management/products/${id}${qs ? `?${qs}` : ''}`,
    );
  };

  return (
    <RecordNavigation
      basePath="/master-data-management/products"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="product"
      className={className}
    />
  );
}
