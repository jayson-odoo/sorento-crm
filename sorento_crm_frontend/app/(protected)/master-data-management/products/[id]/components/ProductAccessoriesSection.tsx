'use client';

import { useState } from 'react';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { useOwnerAccessories } from '../../../accessories/hooks/useAccessories';
import { AccessoryListField } from './AccessoryListField';
import { CopyAccessoriesDialog } from './CopyAccessoriesDialog';

/** "Accessories included": what ships with this product (PRICETAG-ACCESSORIES B1). */
export function ProductAccessoriesSection({ productId }: { productId: string }) {
  const canEdit = useHasPermission('master_data.products.edit');
  const { data, isLoading, isError } = useOwnerAccessories('product', productId);
  const [copyOpen, setCopyOpen] = useState(false);
  const entryCount = (data ?? []).length;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Accessories included</CardTitle>
        {/* ACC-COPY-TO-PRODUCTS: editors only, and only once there is a saved list to copy. */}
        {canEdit && entryCount > 0 ? (
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setCopyOpen(true)}>
            <Copy className="size-4" />
            Copy to other products
          </Button>
        ) : null}
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
      {canEdit && entryCount > 0 ? (
        <CopyAccessoriesDialog
          open={copyOpen}
          onOpenChange={setCopyOpen}
          sourceProductId={productId}
          entryCount={entryCount}
        />
      ) : null}
    </Card>
  );
}

export default ProductAccessoriesSection;
