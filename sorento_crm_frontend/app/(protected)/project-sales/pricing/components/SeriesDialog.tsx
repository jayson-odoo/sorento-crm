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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useProductCategorySelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query';
import { useSeriesMutations } from '../../_shared/hooks/useProjects';
import type { ProjectSeries } from '../../_shared/types/project.types';

/**
 * Define a series by the categories it covers.
 *
 * Categories are nominated, not enumerated: picking a parent covers every category under
 * it, so a series is a handful of picks rather than a list of every SKU that will ever be
 * added to it. The count of what is actually covered is shown after saving, because it is
 * the number that decides which lines get flagged.
 *
 * The category list is sent WHOLE on save rather than as a delta, which is what makes an
 * unticked category actually leave the series.
 */
export function SeriesDialog({
  series,
  onDone,
}: {
  series: ProjectSeries | null;
  onDone: () => void;
}) {
  const { create, update } = useSeriesMutations();
  const brands = useBrandSelectQuery();
  const categories = useProductCategorySelectQuery();

  const [name, setName] = React.useState(series?.name ?? '');
  const [brandId, setBrandId] = React.useState(series?.brand_id ?? '');
  const [description, setDescription] = React.useState(series?.description ?? '');
  const [isActive, setIsActive] = React.useState(series?.is_active ?? true);
  const [categoryIds, setCategoryIds] = React.useState<string[]>(
    series?.category_ids ?? [],
  );

  const isEdit = Boolean(series);
  const pending = create.isPending || update.isPending;

  const categoryOptions = React.useMemo(
    () =>
      (categories.data ?? [])
        .filter((row) => row.is_active || categoryIds.includes(row.id))
        .map((row) => ({
          value: row.id,
          label: row.category_name,
          description: row.category_code,
        })),
    [categories.data, categoryIds],
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit "${series?.name}"` : 'Add a series'}</DialogTitle>
          <DialogDescription>
            Anything a quotation prices outside these categories is flagged as
            non-standard.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              name: name.trim(),
              brand_id: brandId || null,
              description: description.trim() || null,
              is_active: isActive,
              category_ids: categoryIds,
            };
            if (series) {
              await update.mutateAsync({ id: series.id, body });
            } else {
              await create.mutateAsync(body);
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="series-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="series-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Sorento Project Series"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="series-brand">Brand</Label>
              <SearchableSelect
                id="series-brand"
                value={brandId}
                onChange={setBrandId}
                clearable
                options={(brands.data ?? [])
                  .filter((row) => row.is_active || row.id === series?.brand_id)
                  .map((row) => ({
                    value: row.id,
                    label: row.brand_name,
                    description: row.brand_code,
                  }))}
                placeholder="Any brand"
                emptyMessage="No brands found"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="series-categories">Categories covered</Label>
              <SearchableMultiSelect
                value={categoryIds}
                onChange={setCategoryIds}
                options={categoryOptions}
                placeholder="Select categories"
                emptyMessage="No categories found"
              />
              <p className="text-xs text-muted-foreground">
                Picking a parent category also covers everything under it, so there is no
                need to tick each child.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="series-description">Description</Label>
              <Textarea
                id="series-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={2}
                placeholder="What this series is for, and who agreed it"
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
              <div className="min-w-0">
                <Label htmlFor="series-active" className="text-sm">
                  Active
                </Label>
                <p className="text-xs text-muted-foreground">
                  An inactive series stays on the quotations that already use it, but is
                  not offered on new ones.
                </p>
              </div>
              <Switch id="series-active" checked={isActive} onCheckedChange={setIsActive} />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || pending}>
              {isEdit ? 'Save changes' : 'Add series'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
