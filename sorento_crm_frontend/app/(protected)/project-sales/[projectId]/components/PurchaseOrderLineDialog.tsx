'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
// The shared products `/select` mapper. Its name says "variant" because that screen
// needed it first; the endpoint and the shape are the generic ones.
import { getProductsForVariantSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import { usePurchaseOrderLineMutations } from '../../_shared/hooks/useProjects';
import type {
  ProjectPurchaseOrder,
  PurchaseOrderLine,
} from '../../_shared/types/project.types';

/**
 * One line of a customer PO.
 *
 * The product is optional on purpose: contractors order using their own codes, and
 * forcing a match to our catalogue at entry time would mean either a wrong match or an
 * unrecordable PO. An unmatched line is recorded and flagged instead (AC-F9), which is
 * the whole design.
 */
export function PurchaseOrderLineDialog({
  projectId,
  po,
  line,
  nextSortOrder,
  onDone,
}: {
  projectId: string;
  po: ProjectPurchaseOrder;
  line: PurchaseOrderLine | null;
  nextSortOrder: number;
  onDone: () => void;
}) {
  const { create, update } = usePurchaseOrderLineMutations(projectId, po.id);

  const [productId, setProductId] = React.useState(line?.product_id ?? '');
  const [productCode, setProductCode] = React.useState(line?.product_code ?? '');
  const [description, setDescription] = React.useState(line?.description ?? '');
  const [unitPrice, setUnitPrice] = React.useState(line?.unit_price ?? '');
  const [quantity, setQuantity] = React.useState(line?.quantity ?? '1');
  const [uom, setUom] = React.useState(line?.uom ?? '');
  const [notes, setNotes] = React.useState(line?.notes ?? '');

  const isEdit = Boolean(line);
  const pending = create.isPending || update.isPending;
  const blocked = !productId && !productCode.trim();

  const fetchProducts = React.useCallback(async (query: string) => {
    const rows = await getProductsForVariantSelect(query || undefined);
    return rows.map((row) => ({
      value: row.id,
      label: row.product_code,
      description: row.product_name,
    }));
  }, []);

  const selectedProduct = React.useMemo(
    () =>
      line?.product_id
        ? { value: line.product_id, label: line.product_code ?? 'Selected product' }
        : undefined,
    [line],
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit PO line' : 'Add a PO line'}</DialogTitle>
          <DialogDescription>
            Match it to a product where you can. An unmatched line is still recorded, and
            flagged as not quoted.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              product_id: productId || null,
              product_code: productCode.trim() || null,
              description: description.trim() || null,
              unit_price: unitPrice.trim() || '0',
              quantity: quantity.trim() || '1',
              uom: uom.trim() || null,
              notes: notes.trim() || null,
            };
            if (line) {
              await update.mutateAsync({ id: line.id, body });
            } else {
              await create.mutateAsync({ ...body, sort_order: nextSortOrder });
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="po-line-product">Our product</Label>
              <SearchableSelect
                id="po-line-product"
                value={productId}
                onChange={setProductId}
                clearable
                fetchOptions={fetchProducts}
                selectedOption={selectedProduct}
                placeholder="Not matched to our catalogue"
                emptyMessage="No products match"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="po-line-code">
                Code on the PO
                {!productId && <span className="text-destructive"> *</span>}
              </Label>
              <Input
                id="po-line-code"
                value={productCode}
                onChange={(event) => setProductCode(event.target.value)}
                placeholder="What their document calls it"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="po-line-description">Description</Label>
              <Input
                id="po-line-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="As written on the PO"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="po-line-price">Unit price (RM)</Label>
                <Input
                  id="po-line-price"
                  type="number"
                  step="0.01"
                  min="0"
                  value={unitPrice}
                  onChange={(event) => setUnitPrice(event.target.value)}
                  placeholder="0.00"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="po-line-qty">Quantity</Label>
                <Input
                  id="po-line-qty"
                  type="number"
                  step="0.01"
                  min="0"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="po-line-uom">UOM</Label>
                <Input
                  id="po-line-uom"
                  value={uom}
                  onChange={(event) => setUom(event.target.value)}
                  placeholder="PCS"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="po-line-notes">Notes</Label>
              <Textarea
                id="po-line-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={2}
                placeholder="Why the price or the model differs, if it does"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked || pending}>
              {isEdit ? 'Save line' : 'Add line'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
