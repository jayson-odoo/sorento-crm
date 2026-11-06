'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { useOwnerAccessories } from '../../../accessories/hooks/useAccessories';
import { AccessoryListField } from './AccessoryListField';

/** "Accessories included": what ships with this product (PRICETAG-ACCESSORIES B1). */
export function ProductAccessoriesSection({ productId }: { productId: string }) {
  const canEdit = useHasPermission('master_data.products.edit');
  const { data, isLoading, isError } = useOwnerAccessories('product', productId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Accessories included</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <SectionSkeleton rows={2} />
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load the accessories. Try reloading the page.
          </p>
        ) : (data ?? []).length === 0 && !canEdit ? (
          <p className="text-sm font-medium">No accessories</p>
        ) : (
          <>
            {(data ?? []).length === 0 ? (
              <p className="mb-2 text-sm font-medium">No accessories</p>
            ) : null}
            <AccessoryListField
              kind="product"
              ownerId={productId}
              ownerHostId={productId}
              label="Accessories included"
              hideLabel
              canEdit={canEdit}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default ProductAccessoriesSection;
