'use client';

/**
 * The combo as its default price tag template prints it, beside the description editor
 * (PRICETAG-COMBO-FORMAT). Drawn through `DesignViewer`, the renderer the request preview and the
 * PDF use, from the description as typed (before it is saved), so an edit is seen at once.
 */

import { useMemo } from 'react';
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

/** The template a combo prints with by default: its SP default, else its LP default. */
export function defaultLink(rows: ProductTagTemplateItem[]): ProductTagTemplateItem | null {
  return (
    rows.find((row) => row.default_selling) ??
    rows.find((row) => row.default_list) ??
    rows.find((row) => row.is_default) ??
    (rows.length === 1 ? rows[0] : null)
  );
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
  const link = defaultLink(links.data ?? []);
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
    price_type: link?.default_selling ? 'selling' : 'list',
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

  if (links.isLoading || (link?.published && preview.isLoading)) return <SectionSkeleton rows={4} />;
  if (!payload) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center">
        <p className="text-sm text-muted-foreground">
          {link ? 'No published price tag template' : 'No price tag template linked'}
        </p>
      </div>
    );
  }
  return <DesignViewer title="Tag preview" docNumber={combo.name} payload={payload} />;
}

export default ComboTagPreview;
