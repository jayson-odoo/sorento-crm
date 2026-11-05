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
import { usePublishedTagTemplates } from '@/app/(protected)/dealer-kit/hooks/usePublishedTagTemplates';
import { buildSingleTagSheet } from '@/lib/dealer-kit/request-tags';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { ResolvedLineData } from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { ProductTagTemplateItem } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';
import type { ProductComboRow } from '../../types/productCombo.types';

const TAG_ID = 'combo-preview';

/** The template a combo prints with by default: its SP default, else its LP default. */
export function defaultLink(rows: ProductTagTemplateItem[]): ProductTagTemplateItem | null {
  return (
    rows.find((row) => row.default_selling) ??
    rows.find((row) => row.default_list) ??
    rows.find((row) => row.is_default) ??
    (rows.length === 1 ? rows[0] : null)
  );
}

function money(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
  const published = usePublishedTagTemplates();
  const link = defaultLink(links.data ?? []);
  const template = link ? published.data?.find((row) => row.id === link.id) : undefined;

  const payload = useMemo<TagSheetDesignPayload | null>(() => {
    if (!template) return null;
    const doc = buildSingleTagSheet(
      { id: TAG_ID, line: { line_type: 'product', product_id: combo.host_product_id } } as never,
      template,
      () => 'combo-preview-tag',
    );
    const resolved = {
      tag_id: TAG_ID,
      tag_label: '1',
      line_id: TAG_ID,
      code: combo.name,
      name: combo.name,
      dimensions: '',
      spec_lines: '',
      list_price: money(combo.list_price),
      sell_price: money(combo.sell_price),
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      parts: [],
      price_tag_description: null,
      combo: {
        id: combo.id,
        name: combo.name,
        description,
        free_items: combo.free_items ?? null,
        choices: [],
        upgrades: [],
      },
    } as unknown as ResolvedLineData;
    return {
      page_id: TAG_ID,
      version: 0,
      source: 'draft',
      doc,
      resolvedData: { [TAG_ID]: resolved },
      assets: {},
      images: {},
      fonts: [],
    };
  }, [template, combo, description]);

  if (links.isLoading || published.isLoading) return <SectionSkeleton rows={4} />;
  if (!payload) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center">
        <p className="text-sm text-muted-foreground">No price tag template linked</p>
      </div>
    );
  }
  return <DesignViewer title="Tag preview" docNumber={combo.name} payload={payload} />;
}

export default ComboTagPreview;
