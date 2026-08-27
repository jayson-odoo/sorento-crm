'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useMatchSupplierCode } from '../hooks/useSupplierCodeAliases';
import {
  aliasTargetFor,
  fetchProductOrSetOptions,
  renderProductOrSetOption,
} from './productOrSetPicker';

/**
 * "This code is that product" - or that SET - the answer to a supplier code nothing in the
 * catalogue matches (R16, R20).
 *
 * The picker is SERVER-SEARCHED and paginated, and it holds products and product sets in one
 * list. The product master is tens of thousands of rows, and a dropdown holding one cached
 * page silently hides the item the operator is looking for - which is how the same mistake
 * was made twice already; and the supplier sells the whole WC, so `CWC605-RL` names a set no
 * product carries and a products-only list could not express the true answer at all.
 *
 * Kept for the proforma detail's Matched cell, where ONE code is being corrected. The
 * loading plan's queue picks inline instead (R17): a dialog per code turns twenty codes into
 * forty clicks and hides the list being worked down.
 *
 * What the supplier called it is shown beside the code, because that is what the person
 * matching it recognises: `SRTWC286-SH-250UF` means nothing on its own, and "连体马桶,
 * SORENTO" means everything.
 */
export function MatchToProductDialog({
  open,
  onOpenChange,
  supplierId,
  supplierCode,
  supplierLabel,
  onMatched,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  supplierId: string | null;
  /** The code as the supplier wrote it. Null closes the dialog. */
  supplierCode: string | null;
  /** The supplier's own words for the item, when their file gave any. */
  supplierLabel?: string | null;
  onMatched?: () => void;
}) {
  const [productId, setProductId] = useState<string | null>(null);
  const match = useMatchSupplierCode();

  // Cleared on every open: a choice left over from the last code would be one keystroke
  // away from being recorded against this one.
  useEffect(() => {
    if (open) setProductId(null);
  }, [open, supplierCode]);

  const fetchProducts = fetchProductOrSetOptions;

  const submit = async () => {
    if (!supplierId || !supplierCode || !productId) return;
    try {
      await match.mutateAsync({
        supplier_id: supplierId,
        supplier_code: supplierCode,
        ...aliasTargetFor(productId),
      });
      onOpenChange(false);
      onMatched?.();
    } catch {
      // The hook toasts the refusal; the dialog stays open on the choice that was refused.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Match to product or set</DialogTitle>
          <DialogDescription>
            {supplierCode}
            {supplierLabel ? ` - ${supplierLabel}` : ''}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-3">
          <div>
            <Label htmlFor="match-product" className="mb-1 block text-xs">
              Product or set
            </Label>
            <SearchableSelect
              id="match-product"
              value={productId ?? ''}
              onChange={(v: string) => setProductId(v || null)}
              fetchOptions={fetchProducts}
              renderOption={renderProductOrSetOption}
              paginated
              pageSize={50}
              placeholder="Search a product or set code"
              clearable
            />
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!productId || match.isPending}>
            {match.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Match
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default MatchToProductDialog;
