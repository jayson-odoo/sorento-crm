'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useProductSoldWith } from '../../hooks/useProductCombos';

/**
 * "Sold with" (AC-S1-6): the read-only mirror of `ProductCombosSection`, on a
 * PART's own page - so "this basin is part of the 11834 cabinet's 3 in 1" is
 * findable from either side. A part can sit in several combos across several
 * hosts, so every one is named. Editing happens only on the host, where the
 * package is defined.
 */
export function ProductSoldWithSection({ productId }: { productId: string }) {
  const { data: rows, isLoading, isError } = useProductSoldWith(productId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sold with</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <SectionSkeleton rows={2} />
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load what this is sold with. Try reloading the page.
          </p>
        ) : !rows || rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This product is not part of any combo.
          </p>
        ) : (
          <ul className="space-y-2">
            {rows.map((row) => (
              <li key={`${row.combo_id}`} className="rounded-lg border p-3">
                <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
                  <Link
                    href={`/master-data-management/products/${row.host_product_id}`}
                    className="truncate font-medium text-primary hover:underline"
                    title={row.host_code}
                  >
                    {row.host_code}
                  </Link>
                  <span className="text-muted-foreground">·</span>
                  <span className="truncate" title={row.combo_name}>
                    {row.combo_name}
                  </span>
                </div>
                <p className="mt-1 truncate text-sm text-muted-foreground" title={row.host_name}>
                  {row.host_name}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default ProductSoldWithSection;
