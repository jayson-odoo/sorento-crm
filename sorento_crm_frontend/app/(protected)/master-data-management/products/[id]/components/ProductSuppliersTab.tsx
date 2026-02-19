'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { getProductSuppliersByProductId } from '../../../../procurement-management/product-suppliers/services/productSupplierService';

interface ProductSuppliersTabProps {
  productId: string;
}

export default function ProductSuppliersTab({ productId }: ProductSuppliersTabProps) {
  const { data: productSuppliers, isLoading } = useQuery({
    queryKey: ['product-suppliers-view', productId],
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
        <p className="text-sm text-muted-foreground">
          Suppliers linked to this product with configured lead times.
        </p>
      </CardHeader>
      <CardContent>
        {suppliers.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No suppliers configured for this product.</p>
            <p className="text-sm mt-2">Edit the product to add suppliers and lead times.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {suppliers.map((ps) => (
              <div
                key={ps.id}
                className="flex items-center justify-between rounded-lg border p-4"
              >
                <div className="flex items-center gap-3">
                  <Badge variant="secondary">
                    {ps.supplier?.supplier_code || 'N/A'}
                  </Badge>
                  <span className="font-medium">
                    {ps.supplier?.supplier_name || 'Unknown Supplier'}
                  </span>
                  {(ps.standard_lead_time_days !== undefined ||
                    ps.lead_time_days !== undefined) && (
                    <Badge variant="outline" className="text-xs">
                      Lead Time: {ps.standard_lead_time_days ?? ps.lead_time_days} days
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
