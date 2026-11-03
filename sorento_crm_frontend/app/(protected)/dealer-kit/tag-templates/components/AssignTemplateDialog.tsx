'use client';

/**
 * "Assign to products" (PRICETAG-TEMPLATE-PER-PRODUCT R3): add this template to,
 * or remove it from, every product a brand / category / item class / model
 * family filter matches. AND across kinds, OR within one; the live count says
 * how many products the click will touch before it is made. Nothing is sent
 * while the filter is empty.
 */

import { useEffect, useMemo, useState } from 'react';
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
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useProductCategorySelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query';
import { useItemClassSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-item-class-select-query';
import {
  isEmptyAssignFilter,
  listFamilyCodes,
  type TemplateAssignFilter,
} from '../../services/productTagTemplateService';
import { useAssignTemplate, useTemplateAssignPreview } from '../../hooks/useProductTagTemplates';

const EMPTY: TemplateAssignFilter = {
  brand_ids: [],
  category_ids: [],
  item_class_ids: [],
  family_codes: [],
};

interface Props {
  template: { id: string; name: string } | null;
  onClose: () => void;
  /**
   * Remove is an unlink, so it parks with a countdown and a Cancel (D7) - run
   * by the LIST, which outlives this dialog, so closing it cannot cut the
   * countdown short. `count` is how many products the filter unlinks now.
   */
  onRemove: (filter: TemplateAssignFilter, count: number) => void;
}

export function AssignTemplateDialog({ template, onClose, onRemove }: Props) {
  const [filter, setFilter] = useState<TemplateAssignFilter>(EMPTY);
  useEffect(() => {
    if (template) setFilter(EMPTY);
  }, [template]);

  const brands = useBrandSelectQuery();
  const categories = useProductCategorySelectQuery();
  const itemClasses = useItemClassSelectQuery();
  const empty = isEmptyAssignFilter(filter);
  const preview = useTemplateAssignPreview(template?.id ?? null, filter, !!template && !empty);
  const assign = useAssignTemplate(template?.id ?? null);
  const matchedNow = preview.data?.matched ?? 0;
  const alreadyNow = preview.data?.already_linked ?? 0;

  const brandOptions = useMemo(
    () => (brands.data ?? []).map((b) => ({ value: b.id, label: b.brand_name, description: b.brand_code })),
    [brands.data],
  );
  const categoryOptions = useMemo(
    () =>
      (categories.data ?? []).map((c) => ({
        value: c.id,
        label: c.category_name,
        description: c.category_code,
      })),
    [categories.data],
  );
  const classOptions = useMemo(
    () =>
      (itemClasses.data ?? []).map((c) => ({
        value: c.id,
        label: c.item_class_name,
        description: c.item_class_code,
      })),
    [itemClasses.data],
  );

  const set = (key: keyof TemplateAssignFilter) => (value: string[]) =>
    setFilter((prev) => ({ ...prev, [key]: value }));

  const matched = matchedNow;
  const already = alreadyNow;
  const toAdd = matched - already;
  const add = () => assign.mutate({ filter, action: 'add' }, { onSuccess: () => onClose() });
  const remove = () => {
    onRemove(filter, already);
    onClose();
  };

  return (
    <Dialog open={!!template} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="truncate" title={template?.name}>
            Assign {template?.name} to products
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Brands</Label>
            <SearchableMultiSelect
              clearable
              value={filter.brand_ids}
              onChange={set('brand_ids')}
              options={brandOptions}
              loadError={brands.error ?? undefined}
              onRetry={() => void brands.refetch()}
              placeholder="Any brand"
            />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Categories</Label>
            <SearchableMultiSelect
              clearable
              value={filter.category_ids}
              onChange={set('category_ids')}
              options={categoryOptions}
              loadError={categories.error ?? undefined}
              onRetry={() => void categories.refetch()}
              placeholder="Any category"
            />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Item classes</Label>
            <SearchableMultiSelect
              clearable
              value={filter.item_class_ids}
              onChange={set('item_class_ids')}
              options={classOptions}
              loadError={itemClasses.error ?? undefined}
              onRetry={() => void itemClasses.refetch()}
              placeholder="Any item class"
            />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Model families</Label>
            <SearchableMultiSelect
              clearable
              value={filter.family_codes}
              onChange={set('family_codes')}
              selectedOptions={filter.family_codes.map((code) => ({ value: code, label: code }))}
              fetchOptions={async (query) =>
                (await listFamilyCodes(query)).map((code) => ({ value: code, label: code }))
              }
              placeholder="Any model family"
            />
          </div>
          <p className="text-sm sm:col-span-2" aria-live="polite">
            {empty
              ? 'Pick at least one brand, category, item class or model family.'
              : preview.isLoading
                ? 'Counting products...'
                : preview.isError
                  ? 'Could not count the matching products.'
                  : `${matched} ${matched === 1 ? 'product matches' : 'products match'}, ${already} already ${already === 1 ? 'has' : 'have'} this template.`}
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="outline"
            disabled={empty || !preview.data || already === 0 || assign.isPending}
            onClick={remove}
          >
            Remove from {already}
          </Button>
          <Button
            disabled={empty || !preview.data || toAdd <= 0 || assign.isPending}
            onClick={add}
          >
            Add to {toAdd > 0 ? toAdd : 0}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
