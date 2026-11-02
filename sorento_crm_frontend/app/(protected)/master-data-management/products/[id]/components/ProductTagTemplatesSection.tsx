'use client';

/**
 * Product page > Overview > "Price tag templates" (PRICETAG-TEMPLATE-PER-PRODUCT R2).
 *
 * The templates this product may print with: one = a price tag request uses it
 * on its own, several = the salesperson picks, none = the code's family rule.
 * Marketing (`dealer_kit.tag_templates.manage`) edits the set in place; anyone
 * who can see templates reads it. Not drawn at all without that read.
 */

import { useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  usePriceTagTemplateOptions,
  useProductTagTemplates,
  useSetProductTagTemplates,
} from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';

function sizeText(width: number | null | undefined, height: number | null | undefined): string | undefined {
  return width && height ? `${width} x ${height} mm` : undefined;
}

export default function ProductTagTemplatesSection({ productId }: { productId: string }) {
  const canView = useHasPermission('dealer_kit.tag_templates.view');
  const canManage = useHasPermission('dealer_kit.tag_templates.manage');
  const linked = useProductTagTemplates(productId, canView);
  const options = usePriceTagTemplateOptions(canManage);
  const save = useSetProductTagTemplates(productId);

  const selectOptions = useMemo(
    () =>
      (options.data ?? []).map((template) => ({
        value: template.id,
        label: template.name,
        description: [
          sizeText(template.print_size.width_mm, template.print_size.height_mm),
          template.published_version_id ? null : 'Draft',
        ]
          .filter(Boolean)
          .join(' / '),
      })),
    [options.data],
  );

  if (!canView) return null;
  const rows = linked.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Price tag templates</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {linked.isLoading ? (
          <SectionSkeleton rows={2} />
        ) : linked.isError ? (
          <p className="text-sm text-destructive">
            Could not load the price tag templates. Try reloading the page.
          </p>
        ) : canManage ? (
          <SearchableMultiSelect
            clearable
            value={rows.map((row) => row.id)}
            selectedOptions={rows.map((row) => ({
              value: row.id,
              label: row.name,
              description: sizeText(row.width_mm, row.height_mm),
            }))}
            onChange={(ids) => save.mutate(ids)}
            options={selectOptions}
            loadError={options.error ?? undefined}
            onRetry={() => void options.refetch()}
            disabled={save.isPending}
            placeholder="Search templates"
            emptyMessage="No templates."
          />
        ) : rows.length === 0 ? null : (
          <div className="flex flex-wrap gap-1.5">
            {rows.map((row) => (
              <Badge key={row.id} variant="secondary" className="font-normal" title={row.name}>
                <span className="max-w-[16rem] truncate">{row.name}</span>
                {row.published ? null : <span className="ml-1 text-muted-foreground">(Draft)</span>}
              </Badge>
            ))}
          </div>
        )}
        {!linked.isLoading && !linked.isError && rows.length === 0 ? (
          <div>
            <p className="text-sm font-medium">No price tag templates</p>
            <p className="text-sm text-muted-foreground">
              Requests for this product use the template that matches its code.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
