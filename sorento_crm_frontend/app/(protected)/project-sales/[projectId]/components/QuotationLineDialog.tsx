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
import { useQuotationLineMutations } from '../../_shared/hooks/useProjects';
import type { QuotationLine, UnitType } from '../../_shared/types/project.types';

const UNIT_TYPE_OPTIONS: { value: UnitType; label: string; description: string }[] = [
  { value: 'house_unit', label: 'Per house unit', description: 'Multiplied by the unit count' },
  { value: 'bathroom', label: 'Per bathroom', description: 'Multiplied by bathrooms per unit' },
  { value: 'facility', label: 'Per facility', description: 'Gym, pool, surau' },
  { value: 'common_area', label: 'Common area', description: 'Priced once for the whole site' },
];

/**
 * Add or edit one line of the current version.
 *
 * The floor is deliberately NOT evaluated here. Resolving it means walking the category
 * ancestry, and a second implementation in the browser would eventually disagree with
 * the server's -- so the price is sent, and the answer that comes back is what the line
 * shows. The dialog's job is to make that answer visible, not to predict it.
 *
 * Leaving the product empty is allowed and gives an off-catalog line, which is always
 * non-standard (AC-E5) and needs its own description because there is no product to
 * borrow one from.
 */
export function QuotationLineDialog({
  projectId,
  versionId,
  line,
  nextSortOrder,
  onDone,
}: {
  projectId: string;
  versionId: string;
  line: QuotationLine | null;
  nextSortOrder: number;
  onDone: () => void;
}) {
  const { create, update } = useQuotationLineMutations(projectId, versionId);

  const [productId, setProductId] = React.useState(line?.product_id ?? '');
  const [description, setDescription] = React.useState(line?.description ?? '');
  const [unitPrice, setUnitPrice] = React.useState(line?.unit_price ?? '');
  const [quantity, setQuantity] = React.useState(line?.quantity ?? '1');
  const [uom, setUom] = React.useState(line?.uom ?? '');
  const [unitType, setUnitType] = React.useState<string>(line?.unit_type ?? '');
  const [notes, setNotes] = React.useState(line?.notes ?? '');

  const isEdit = Boolean(line);
  const pending = create.isPending || update.isPending;
  // Off-catalog lines carry the description the customer reads, so it is the one thing
  // that cannot be left out.
  const blocked = !productId && !description.trim();

  const fetchProducts = React.useCallback(async (query: string) => {
    const rows = await getProductsForVariantSelect(query || undefined);
    return rows.map((row) => ({
      value: row.id,
      label: row.product_code,
      description: row.product_name,
    }));
  }, []);

  // Async mode fetches one page at a time, so the line's own product has to be handed in
  // or the trigger would read as empty on an existing line until the user searches for it.
  const selectedProduct = React.useMemo(
    () =>
      line?.product_id
        ? {
            value: line.product_id,
            label: line.product_code ?? 'Selected product',
            description: line.description ?? undefined,
          }
        : undefined,
    [line],
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit line' : 'Add a line'}</DialogTitle>
          <DialogDescription>
            Pick a product and its code, description and list price are frozen onto the
            line. Leave it empty for something that is not in the catalogue.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              product_id: productId || null,
              description_snapshot: description.trim() || null,
              unit_price: unitPrice.trim() || '0',
              quantity: quantity.trim() || '1',
              uom: uom.trim() || null,
              unit_type: (unitType || null) as UnitType | null,
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
              <Label htmlFor="line-product">Product</Label>
              <SearchableSelect
                id="line-product"
                value={productId}
                onChange={setProductId}
                clearable
                fetchOptions={fetchProducts}
                selectedOption={selectedProduct}
                placeholder="Off-catalog line"
                emptyMessage="No products match"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="line-description">
                Description
                {!productId && <span className="text-destructive"> *</span>}
              </Label>
              <Input
                id="line-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder={
                  productId
                    ? "Leave empty to use the product's own description"
                    : 'Wall-hung WC, matte black, supply only'
                }
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="line-unit-price">Unit price (RM)</Label>
                <Input
                  id="line-unit-price"
                  type="number"
                  step="0.01"
                  min="0"
                  value={unitPrice}
                  onChange={(event) => setUnitPrice(event.target.value)}
                  placeholder="0.00"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="line-quantity">Quantity</Label>
                <Input
                  id="line-quantity"
                  type="number"
                  step="0.01"
                  min="0"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="line-uom">Unit of measure</Label>
                <Input
                  id="line-uom"
                  value={uom}
                  onChange={(event) => setUom(event.target.value)}
                  placeholder={productId ? "The product's own UOM" : 'PCS'}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="line-unit-type">Counts per</Label>
                <SearchableSelect
                  id="line-unit-type"
                  value={unitType}
                  onChange={setUnitType}
                  clearable
                  options={UNIT_TYPE_OPTIONS}
                  placeholder="Not counted per unit"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="line-notes">Notes</Label>
              <Textarea
                id="line-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={2}
                placeholder="Why this price, what was agreed, what it replaces"
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
