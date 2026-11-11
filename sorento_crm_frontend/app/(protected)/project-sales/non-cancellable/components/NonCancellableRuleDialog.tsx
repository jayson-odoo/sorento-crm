'use client';

import * as React from 'react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { getProductsForLineSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import { useProductCategorySelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query';
import { useNonCancellableRuleMutations } from '../../_shared/hooks/useProjects';
import type { NonCancellableRule } from '../../_shared/types/project.types';

type Kind = 'product' | 'category';

/** Add or edit one company default. The target is fixed once saved; only the answer and notes move. */
export function NonCancellableRuleDialog({
  rule,
  onDone,
}: {
  rule: NonCancellableRule | null;
  onDone: () => void;
}) {
  const { create, update } = useNonCancellableRuleMutations();
  const categories = useProductCategorySelectQuery();
  const [kind, setKind] = React.useState<Kind>(rule?.category_id ? 'category' : 'product');
  const [productId, setProductId] = React.useState(rule?.product_id ?? '');
  const [categoryId, setCategoryId] = React.useState(rule?.category_id ?? '');
  const [nonCancellable, setNonCancellable] = React.useState(rule?.non_cancellable ?? true);
  const [notes, setNotes] = React.useState(rule?.notes ?? '');
  const pending = create.isPending || update.isPending;

  const fetchProducts = React.useCallback(async (query: string) => {
    const products = await getProductsForLineSelect(query || undefined);
    return products.map((product) => ({
      value: product.id,
      label: product.product_code,
      description: product.product_name,
    }));
  }, []);

  const categoryOptions = React.useMemo(
    () =>
      (categories.data ?? []).map((category) => ({
        value: category.id,
        label: category.category_name,
        description: category.category_code,
      })),
    [categories.data],
  );

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!rule && kind === 'product' && !productId) {
      toast.error('Pick a product');
      return;
    }
    if (!rule && kind === 'category' && !categoryId) {
      toast.error('Pick a category');
      return;
    }
    try {
      if (rule) {
        await update.mutateAsync({
          id: rule.id,
          body: { non_cancellable: nonCancellable, notes: notes.trim() || null },
        });
      } else {
        await create.mutateAsync({
          ...(kind === 'product' ? { product_id: productId } : { category_id: categoryId }),
          non_cancellable: nonCancellable,
          notes: notes.trim() || null,
        });
      }
      onDone();
    } catch {
      // toasted by the mutation; the dialog stays open with what was typed
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onDone()}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{rule ? 'Edit item' : 'Add item'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="nc-kind">Type</Label>
              <SearchableSelect
                id="nc-kind"
                value={kind}
                disabled={Boolean(rule)}
                onChange={(next) => setKind((next as Kind) || 'product')}
                options={[
                  { value: 'product', label: 'Product' },
                  { value: 'category', label: 'Category' },
                ]}
              />
            </div>

            {kind === 'product' ? (
              <div className="space-y-1.5">
                <Label htmlFor="nc-product">Product</Label>
                <SearchableSelect
                  id="nc-product"
                  value={productId}
                  disabled={Boolean(rule)}
                  onChange={setProductId}
                  fetchOptions={fetchProducts}
                  selectedOption={
                    rule?.product_id && rule.product_code
                      ? {
                          value: rule.product_id,
                          label: rule.product_code,
                          description: rule.product_name ?? undefined,
                        }
                      : undefined
                  }
                  placeholder="Pick a product"
                />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="nc-category">Category</Label>
                <SearchableSelect
                  id="nc-category"
                  value={categoryId}
                  disabled={Boolean(rule)}
                  onChange={setCategoryId}
                  loadError={categories.error}
                  onRetry={() => void categories.refetch()}
                  options={categoryOptions}
                  placeholder="Pick a category"
                />
              </div>
            )}

            <div className="flex items-center gap-3">
              <Switch
                id="nc-flag"
                checked={nonCancellable}
                onCheckedChange={setNonCancellable}
                aria-label="Non-cancellable"
              />
              <Label htmlFor="nc-flag">{nonCancellable ? 'Non-cancellable: Yes' : 'Non-cancellable: No'}</Label>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="nc-notes">Notes</Label>
              <Textarea
                id="nc-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={3}
              />
            </div>
          </DialogBody>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {rule ? 'Save' : 'Add item'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
