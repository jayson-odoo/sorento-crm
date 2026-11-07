'use client';

/**
 * The combo as its default price tag template prints it, beside the description editor
 * (PRICETAG-COMBO-FORMAT). Drawn through `DesignViewer`, the renderer the request preview and the
 * PDF use, from the description as typed (before it is saved), so an edit is seen at once.
 */

import { useEffect, useMemo, useState } from 'react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import { useComboTagTemplates } from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';
import { useTagPreview } from '@/app/(protected)/dealer-kit/hooks/useTagPreview';
import { buildSingleTagSheet } from '@/lib/dealer-kit/request-tags';
import { designPayloadFromResponse, type TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { TagPreviewLineInput } from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { ProductTagTemplateItem } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';
import type { ProductComboRow } from '../../types/productCombo.types';

const KEY = 'combo-preview';

/**
 * The linked templates in the switcher's order (TAG-TEMPLATE-DUPLICATE item 4, owner 6 Nov):
 * the Default LP first, then the Default SP, then the rest as linked. The first is the one the
 * preview opens on.
 */
export function orderedLinks(rows: ProductTagTemplateItem[]): ProductTagTemplateItem[] {
  const rank = (row: ProductTagTemplateItem) =>
    row.default_list ? 0 : row.default_selling ? 1 : row.is_default ? 2 : 3;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => rank(a.row) - rank(b.row) || a.index - b.index)
    .map(({ row }) => row);
}

/** The price a link is previewed at: the LP default as list, the SP default as selling, else
 *  the template's own price type (unset or LP & SP read as list). */
function previewPriceType(link: ProductTagTemplateItem): 'list' | 'selling' {
  if (link.default_list) return 'list';
  if (link.default_selling) return 'selling';
  return link.price_type === 'selling' ? 'selling' : 'list';
}

/** "Default LP", "Default SP" or nothing: what the switcher says beside a template's name. */
function defaultTag(link: ProductTagTemplateItem): string | null {
  if (link.default_list && link.default_selling) return 'Default LP & SP';
  if (link.default_list) return 'Default LP';
  if (link.default_selling) return 'Default SP';
  return null;
}

export function ComboTagPreview({
  combo,
  description,
}: {
  combo: ProductComboRow;
  /** The description as it stands in the editor. */
  description: string | null;
}) {
  const links = useComboTagTemplates(combo.id);
  const ordered = useMemo(() => orderedLinks(links.data ?? []), [links.data]);
  // The reader's pick among the linked templates; falls back to the first (Default LP) when
  // nothing is picked yet or the picked one was unlinked.
  const [pickedId, setPickedId] = useState<string | null>(null);
  useEffect(() => {
    if (pickedId && !ordered.some((row) => row.id === pickedId)) setPickedId(null);
  }, [ordered, pickedId]);
  const link = ordered.find((row) => row.id === pickedId) ?? ordered[0] ?? null;
  const line: TagPreviewLineInput = {
    key: KEY,
    line_type: 'product',
    product_id: combo.host_product_id,
    product_set_id: null,
    combo_id: combo.id,
    parts: [],
    promotion_id: null,
    manual_sell_price: null,
    tag_template_id: link?.id ?? null,
    price_type: link ? previewPriceType(link) : 'list',
  };
  // The server draws the line (slots, parts, photos, prices) exactly as the request preview and
  // the PDF do; only a published default can be drawn.
  const preview = useTagPreview(line, !!link && link.published);

  const payload = useMemo<TagSheetDesignPayload | null>(() => {
    const row = preview.data?.lines[0];
    const template = preview.data?.templates[KEY];
    if (!preview.data || !row || !template) return null;
    const tagId = row.tag_id ?? row.line_id ?? KEY;
    const doc = buildSingleTagSheet(
      {
        id: tagId,
        quantity: 1,
        line: {
          id: row.line_id ?? KEY,
          line_type: 'product',
          product_id: combo.host_product_id,
          product_set_id: null,
          quantity: 1,
        },
      },
      template,
      () => 'combo-preview-tag',
    );
    // Only the description is the editor's unsaved draft; everything else is the server's.
    const drawn = {
      ...row,
      combo: {
        id: combo.id,
        name: combo.name,
        free_items: null,
        accessories: [],
        choices: [],
        upgrades: [],
        ...(row.combo ?? {}),
        description,
      },
    };
    return designPayloadFromResponse({
      doc,
      lines: [drawn],
      assets: preview.data.assets,
      images: preview.data.images,
      fonts: preview.data.fonts,
    });
  }, [preview.data, combo, description]);

  // The switcher (item 4), shown only when there is a choice to make. "Open" in the viewer opens
  // whatever is drawn, so it opens the selected template.
  const switcher =
    ordered.length > 1 ? (
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        aria-label="Template to preview"
        value={link?.id ?? ''}
        onValueChange={(value) => {
          if (value) setPickedId(value);
        }}
        className="flex-wrap"
      >
        {ordered.map((row) => {
          const tag = defaultTag(row);
          return (
            <ToggleGroupItem
              key={row.id}
              value={row.id}
              aria-label={tag ? `${row.name} (${tag})` : row.name}
              title={tag ? `${row.name} (${tag})` : row.name}
              className="max-w-48 px-2 text-xs"
            >
              <span className="truncate">{row.name}</span>
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    ) : null;

  if (links.isLoading || (link?.published && preview.isLoading)) return <SectionSkeleton rows={4} />;
  if (links.isError || preview.isError) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center">
        <p className="text-sm text-muted-foreground">Could not load the tag preview</p>
      </div>
    );
  }
  if (!payload) {
    return (
      <div className="space-y-2">
        {switcher}
        <div className="rounded-lg border border-dashed p-4 text-center">
          <p className="text-sm text-muted-foreground">
            {link ? 'No published price tag template' : 'No price tag template linked'}
          </p>
        </div>
      </div>
    );
  }
  return (
    <DesignViewer
      title="Tag preview"
      docNumber={link ? `${combo.name} - ${link.name}` : combo.name}
      payload={payload}
      headerActions={switcher}
    />
  );
}

export default ComboTagPreview;
