'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useProductOptions, useWarehouseOptions } from '../../hooks/useScmOptions';

/** Manual-plan inputs (M8-D5, revised): warehouse(s) + budget ONLY. No market-insight
 *  toggle - market never enters a run; it reaches the plan only through the chat
 *  (Slice E). The legacy `buy_scope` is removed. Warehouse is now MULTI-select (pick
 *  several, or Select all) so a manual run can cover any subset like the daily run. */
export interface ManualPlanInputs {
  warehouse_codes: string[];
  /**
   * Optional product scope (AC-B8a). **Empty means all products**, so the existing
   * behaviour and the scheduled daily run are unchanged. Human product codes, never
   * ids. This is an explicit product list and NOT a reinstatement of the removed
   * `buy_scope` category filter.
   */
  product_codes: string[];
  budget: number;
}

/**
 * SCM M8 (slice D) - "Manual plan" on-demand run inputs. The scheduled daily run
 * (all warehouses, full budget) fires without this modal; this is the manual
 * override. Prototype: submitting just closes and re-shows the mock plan.
 */
export function RunPlanningModal({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (inputs: ManualPlanInputs) => void;
  isSubmitting: boolean;
}) {
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [products, setProducts] = useState<string[]>([]);
  const [budget, setBudget] = useState('72000');
  const [error, setError] = useState<string | null>(null);

  const {
    data: warehouseOptions,
    isLoading: warehousesLoading,
    isError: warehousesError,
  } = useWarehouseOptions();

  const {
    data: productOptions,
    isLoading: productsLoading,
    isError: productsError,
  } = useProductOptions();

  const allCodes = (warehouseOptions ?? []).map((o) => o.value);
  const allSelected = allCodes.length > 0 && warehouses.length === allCodes.length;

  useEffect(() => {
    if (!open) return;
    setWarehouses([]);
    setProducts([]);
    setBudget('72000');
    setError(null);
  }, [open]);

  const submit = () => {
    setError(null);
    if (warehouses.length === 0) {
      setError('Select at least one warehouse to plan for.');
      return;
    }
    onSubmit({
      warehouse_codes: warehouses,
      // Empty = all products. Products are deliberately NOT required: narrowing to
      // one is the exception, and forcing a pick would make every run harder than
      // the daily one it stands in for.
      product_codes: products,
      budget: Number(budget) || 0,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Manual plan</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-5">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Warehouses</Label>
              <button
                type="button"
                className="text-2xs font-medium text-primary underline-offset-2 hover:underline disabled:opacity-50"
                disabled={warehousesLoading || allCodes.length === 0}
                onClick={() => setWarehouses(allSelected ? [] : allCodes)}
              >
                {allSelected ? 'Clear all' : 'Select all'}
              </button>
            </div>
            <SearchableMultiSelect
              value={warehouses}
              onChange={setWarehouses}
              options={warehouseOptions ?? []}
              disabled={warehousesLoading}
              placeholder={warehousesLoading ? 'Loading warehouses...' : 'Select warehouses'}
              emptyMessage={warehousesError ? 'Could not load warehouses.' : 'No warehouses found.'}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Pick one or more warehouses, or Select all. The scheduled daily run always covers all
              warehouses.
            </p>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label>Products</Label>
              {products.length ? (
                <button
                  type="button"
                  className="text-2xs font-medium text-primary underline-offset-2 hover:underline"
                  onClick={() => setProducts([])}
                >
                  Clear all
                </button>
              ) : null}
            </div>
            <SearchableMultiSelect
              value={products}
              onChange={setProducts}
              options={productOptions ?? []}
              disabled={productsLoading}
              placeholder={productsLoading ? 'Loading products...' : 'All products'}
              emptyMessage={productsError ? 'Could not load products.' : 'No products found.'}
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              Leave empty to plan every product.
            </p>
          </div>

          <div>
            <Label htmlFor="manual-budget" className="mb-1 block">
              Cash budget (RM)
            </Label>
            <Input
              id="manual-budget"
              type="number"
              inputMode="numeric"
              min={0}
              step={500}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className="tabular-nums"
            />
            <p className="mt-1 text-2xs text-muted-foreground">
              You can tighten this on the plan afterwards to defer lower-ranked buys.
            </p>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={isSubmitting}>
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Generate plan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
