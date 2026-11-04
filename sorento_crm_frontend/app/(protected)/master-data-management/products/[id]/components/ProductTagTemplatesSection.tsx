'use client';

/**
 * Product page > Overview > "Price tag templates" (PRICETAG-TEMPLATE-PER-PRODUCT R2).
 *
 * The templates this product may print with: one = a price tag request uses it
 * on its own, several = the salesperson picks, none = no template: the request
 * goes to marketing (no fallback, #2101).
 * Marketing (`dealer_kit.tag_templates.manage`) edits the set in place; anyone
 * who can see templates reads it. Not drawn at all without that read.
 */

import { clickToken } from '@/lib/click-token';
import { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  productTagTemplatesKey,
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
  // Adding a template saves at once; unticking one is an unlink, so it parks
  // with a countdown and a Cancel (D7) and the server commits it.
  const [unlink, setUnlink] = useState<{ batchId: string; ids: string[]; subject: string } | null>(
    null,
  );
  const unlinking = useDeferredAction({
    actionKey: 'product.unlink_tag_templates',
    entityType: 'product',
    entityId: unlink ? productId : null,
    verb: 'Unlinking',
    subject: unlink?.subject ?? '',
    surface: 'toast',
    successMessage: 'Template unlinked',
    payload: { template_ids: unlink?.ids ?? [] },
    invalidateKeys: [productTagTemplatesKey(productId)],
  });
  useEffect(() => {
    if (unlink) unlinking.start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlink?.batchId]);

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
  const defaultId = rows.find((row) => row.is_default)?.id ?? null;

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
            onChange={(ids) => {
              const current = rows.map((row) => row.id);
              const added = ids.filter((id) => !current.includes(id));
              const removed = current.filter((id) => !ids.includes(id));
              // Keep every current link on the add: the removed ones go through
              // the countdown below, not this save.
              if (added.length > 0) {
                save.mutate({
                  template_ids: [...current, ...added],
                  default_template_id: defaultId,
                });
              }
              if (removed.length > 0) {
                const names = rows.filter((row) => removed.includes(row.id)).map((row) => row.name);
                setUnlink({
                  batchId: clickToken(),
                  ids: removed,
                  subject: names.length === 1 ? names[0] : `${names.length} templates`,
                });
              }
            }}
            options={selectOptions}
            loadError={options.error ?? undefined}
            onRetry={() => void options.refetch()}
            disabled={save.isPending || unlinking.isPending}
            placeholder="Search templates"
            emptyMessage="No templates."
          />
        ) : rows.length === 0 ? null : (
          <div className="flex flex-wrap gap-1.5">
            {rows.map((row) => (
              <Badge key={row.id} variant="secondary" className="font-normal" title={row.name}>
                <span className="max-w-[16rem] truncate">{row.name}</span>
                {row.published ? null : <span className="ml-1 text-muted-foreground">(Draft)</span>}
                {row.is_default && rows.length > 1 ? <span className="ml-1">Default</span> : null}
              </Badge>
            ))}
          </div>
        )}
        {canManage && !linked.isLoading && !linked.isError && rows.length > 1 ? (
          <SearchableSelect
            clearable
            value={defaultId ?? ''}
            onChange={(id) =>
              save.mutate({ template_ids: rows.map((row) => row.id), default_template_id: id || null })
            }
            options={rows.map((row) => ({ value: row.id, label: row.name }))}
            disabled={save.isPending}
            placeholder="Default template"
            emptyMessage="No templates."
          />
        ) : null}
        {!linked.isLoading && !linked.isError && rows.length === 0 ? (
          <div>
            <p className="text-sm font-medium">No tag template yet</p>
            <p className="text-sm text-muted-foreground">
              Price tag requests for this product go to marketing to pick one.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
