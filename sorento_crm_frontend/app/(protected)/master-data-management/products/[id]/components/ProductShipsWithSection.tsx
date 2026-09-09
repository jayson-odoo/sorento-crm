'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useCompanionRulesForHost } from '../../hooks/useProductCompanions';

interface ProductShipsWithSectionProps {
  hostProductId: string;
}

/**
 * "Ships with" (UAC A5): the read-only mirror of `ProductSuppliedWithSection`, on a
 * HOST product's own Suppliers tab - so the fact ("this ships with a seat cover, and
 * never gets its own PO line") is findable from either side. Configured only from the
 * companion's own page; a pair rule (SC-RL with X + Y) names the OTHER host too, so
 * whichever half of the pair you are on, you can see it takes both.
 */
export function ProductShipsWithSection({ hostProductId }: ProductShipsWithSectionProps) {
  const { data: rules, isLoading, isError } = useCompanionRulesForHost(hostProductId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ships with</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load "ships with" rules. Try reloading the page.
          </p>
        ) : !rules || rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing rides inside this product's own line.
          </p>
        ) : (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div key={rule.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Link
                    href={`/master-data-management/products/${rule.companion_product_id}`}
                    className="truncate font-medium text-primary hover:underline"
                    title={rule.companion_item_code}
                  >
                    {rule.companion_item_code}
                  </Link>
                  {rule.hosts.length > 1 ? (
                    <span className="text-xs text-muted-foreground">
                      also requires{' '}
                      {rule.hosts
                        .filter((h) => h.product_id !== hostProductId)
                        .map((h) => h.item_code)
                        .join(' + ')}
                    </span>
                  ) : null}
                  {!rule.is_active ? (
                    <Badge variant="secondary" appearance="light" size="sm">
                      Inactive
                    </Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Ratio {rule.ratio}
                  {rule.supplier_name ? ` · ${rule.supplier_code} - ${rule.supplier_name}` : ' · Any supplier'}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ProductShipsWithSection;
