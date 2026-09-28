'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { getProductSuppliersByProductId } from '../../../../procurement-management/product-suppliers/services/productSupplierService';
import { formatPlainDate } from '../../../../procurement-management/cost-price-uploads/lib/formatPlainDate';
import type { CostRowStatus } from '../../../../procurement-management/cost-price-uploads/types/costPrice.types';
import { ProductSuppliedWithSection } from './ProductSuppliedWithSection';
import { ProductShipsWithSection } from './ProductShipsWithSection';

interface ProductSuppliersTabProps {
  productId: string;
}

const STATUS_LABELS: Record<CostRowStatus, string> = {
  in_force: 'In force',
  scheduled: 'Scheduled',
  ended: 'Ended',
  always: 'Always',
  overridden: 'Overridden',
};
const STATUS_BADGE_VARIANT: Record<CostRowStatus, 'success' | 'info' | 'secondary'> = {
  in_force: 'success',
  scheduled: 'info',
  ended: 'secondary',
  always: 'secondary',
  overridden: 'secondary',
};

/** A dash is "not on file", which is a different fact from zero and must not read as it. */
function fmtTerm(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm tabular-nums" title={value}>
        {value}
      </dd>
    </div>
  );
}

export default function ProductSuppliersTab({ productId }: ProductSuppliersTabProps) {
  const [search, setSearch] = useState('');
  const { data: productSuppliers, isLoading, isError, error } = useQuery({
    queryKey: ['product-suppliers', productId],
    queryFn: () => getProductSuppliersByProductId(productId),
    enabled: !!productId,
  });

  const suppliers = productSuppliers || [];

  const tokens = search.toLowerCase().split(/\s+/).filter(Boolean);
  const visible = useMemo(() => {
    if (!tokens.length) return suppliers;
    return suppliers.filter((ps) => {
      const haystack = [
        ps.supplier?.supplier_name,
        ps.supplier?.supplier_code,
        ps.supplier_item_code,
        ...(ps.costs ?? []).map((c) => c.source?.code),
      ]
        .filter(Boolean)
        .map((s) => (s as string).toLowerCase());
      return tokens.every((t) => haystack.some((h) => h.includes(t)));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suppliers, search]);

  return (
    <div className="space-y-6">
      {isLoading ? (
        <Card>
          <CardHeader>
            <CardTitle>Suppliers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Suppliers</CardTitle>
            {suppliers.length > 0 ? (
              <ListSearchInput
                value={search}
                onChange={setSearch}
                placeholder="Search supplier or upload code"
                className="w-full sm:w-80"
              />
            ) : null}
          </CardHeader>
          <CardContent>
            {isError ? (
              <div className="text-center py-8 text-muted-foreground">
                <p>{error instanceof Error ? error.message : 'Failed to load suppliers for this product.'}</p>
              </div>
            ) : suppliers.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <p>No suppliers configured for this product.</p>
                <p className="text-sm mt-2">Edit the product to add suppliers and their terms.</p>
              </div>
            ) : visible.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <p>No supplier matches your search.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {visible.map((ps) => {
                  const costs = ps.costs ?? [];
                  return (
                    <div key={ps.id} className="rounded-lg border p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary">{ps.supplier?.supplier_code || 'N/A'}</Badge>
                        <span className="font-medium">
                          {ps.supplier?.supplier_name || 'Unknown Supplier'}
                        </span>
                        {ps.is_primary_supplier ? (
                          <Badge variant="primary" appearance="light" size="sm">
                            primary
                          </Badge>
                        ) : null}
                      </div>
                      {/* The same terms the edit view holds, in the same order, so a value
                          the buyer set is where they expect to read it back. A dash means the
                          term is not on file, which for the price is why the reorder plan cannot
                          cost this supplier. "Their code" is the supplier's own spelling of this
                          product's code, from a manual match on the loading plan (S4) - read-only
                          here, it is set on the plan's Supplier codes tab, not on this form. */}
                      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                        <Term label="Lead time (days)"
                              value={fmtTerm(ps.standard_lead_time_days ?? ps.lead_time_days)} />
                        <Term label="Unit cost" value={fmtTerm(ps.unit_cost)} />
                        <Term label="Currency" value={fmtTerm(ps.currency)} />
                        <Term label="Minimum order" value={fmtTerm(ps.moq)} />
                        <Term label="Order multiple" value={fmtTerm(ps.order_multiple)} />
                        <Term label="Their code" value={fmtTerm(ps.supplier_item_code)} />
                      </dl>

                      {/* Cost lists (AC-CL-08): the price in force above is already this
                          link's OWN currency, never MYR; these are the dated rows behind
                          it, same columns as the supplier's own Prices tab. */}
                      {costs.length > 0 ? (
                        <div className="mt-3 space-y-1 border-t pt-3">
                          {costs.map((cost) => (
                            <div key={cost.id} className="flex flex-wrap items-center gap-2 text-sm">
                              {/* Round 8: a cost is per packaging method; say which. */}
                              <span className="text-muted-foreground">{cost.packaging_method ?? 'standard'}</span>
                              <span className="tabular-nums font-medium">
                                {cost.unit_cost.toFixed(2)} {cost.currency}
                              </span>
                              <span className="text-muted-foreground">
                                {formatPlainDate(cost.start_date) ?? 'Always'} to {formatPlainDate(cost.end_date) ?? 'no end'}
                              </span>
                              <Badge variant={STATUS_BADGE_VARIANT[cost.status]}>{STATUS_LABELS[cost.status]}</Badge>
                              <span className="text-muted-foreground">
                                {cost.source ? cost.source.code : 'Edited by hand'}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* PLAN-scm-supplied-with-companions.md: this product's own bundling rules
          ("Supplied with", it is the companion) and the mirror of anyone else's
          ("Ships with", it is a host). A product can be both at once, so both
          sections render unconditionally, each with its own empty state. */}
      <ProductSuppliedWithSection companionProductId={productId} />
      <ProductShipsWithSection hostProductId={productId} />
    </div>
  );
}
