'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { getProductSuppliersByProductId } from '../../../../procurement-management/product-suppliers/services/productSupplierService';
import type { ProductSupplier } from '../../../../procurement-management/product-suppliers/types/productSupplier.types';

interface ProductSuppliersTabProps {
  productId: string;
}

// PHASE 1 MOCK (S4, AC-D2): the backend does not read `supplier_item_code` off the alias
// table yet - Phase 2 joins `scm.supplier_product_code_alias` on the by-product route. Stands
// in for one row so both the value and the empty-state dash (ADR 1e) are visible; deleted
// with this comment once the real field is on the wire.
function mockTheirCode(ps: ProductSupplier, index: number): string | null {
  if (ps.supplier_item_code !== undefined) return ps.supplier_item_code ?? null;
  return index === 0 ? 'JBC-9042' : null;
}

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
  const { data: productSuppliers, isLoading } = useQuery({
    queryKey: ['product-suppliers', productId],
    queryFn: () => getProductSuppliersByProductId(productId),
    enabled: !!productId,
  });

  if (isLoading) {
    return (
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
    );
  }

  const suppliers = productSuppliers || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suppliers</CardTitle>
      </CardHeader>
      <CardContent>
        {suppliers.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No suppliers configured for this product.</p>
            <p className="text-sm mt-2">Edit the product to add suppliers and their terms.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {suppliers.map((ps, index) => (
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
                  <Term label="Their code" value={fmtTerm(mockTheirCode(ps, index))} />
                </dl>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
