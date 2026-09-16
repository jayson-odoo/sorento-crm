/**
 * Combo subject picker on every product-bound layer (F3, D7, AC-S4-1/S4-2).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-line-promo-combo-subject-acceptance-criteria.md`
 * AC-S4-1: on a combo tag, every product-bound layer (product_slot, a text
 * layer with a `{{product.*}}`/`{{spec.*}}` token, price_badge, barcode)
 * shows a Product select. AC-S4-2: a single-product tag (no parts) shows it
 * on NONE of them.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import type { TagLayer, TagLayerProps, TagPartData } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const PART: TagPartData = {
  product_id: 'prod-tap',
  code: 'SRTTAP100',
  name: 'ZZT Kitchen Tap',
  dimensions: '',
  spec_lines: [],
  images: [],
  barcode: null,
  list_price: 100,
  sell_price: 80,
};

function baseLayer(overrides: Partial<TagLayer> = {}): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'text', text: 'Hello' } as TagLayerProps,
    ...overrides,
  } as TagLayer;
}

function renderPanel(layer: TagLayer, parts: TagPartData[]) {
  render(
    <InspectorPanel
      layer={layer}
      onUpdate={vi.fn()}
      onUpdateProps={vi.fn()}
      subjectParts={parts}
      subjectParentCode="SRTHOST01"
    />,
  );
}

describe('InspectorPanel - combo subject picker on every product-bound layer (F3, AC-S4-1)', () => {
  it('shows the Product select for a product_slot layer on a tag whose line has parts', () => {
    const layer = baseLayer({
      type: 'product_slot',
      slot_binding: 'product_image',
      props: { kind: 'product_slot', fieldKey: 'product_image' } as TagLayerProps,
    });
    renderPanel(layer, [PART]);
    expect(screen.getByRole('heading', { level: 4, name: 'Product' })).toBeInTheDocument();
  });

  it('shows the Product select for a text layer whose text contains {{product.code}}', () => {
    const layer = baseLayer({
      type: 'text',
      props: { kind: 'text', text: 'Code {{product.code}}' } as TagLayerProps,
    });
    renderPanel(layer, [PART]);
    expect(screen.getByRole('heading', { level: 4, name: 'Product' })).toBeInTheDocument();
  });

  it('shows the Product select for a barcode layer', () => {
    const layer = baseLayer({
      type: 'barcode',
      slot_binding: 'barcode',
      props: { kind: 'barcode', show_code: true } as TagLayerProps,
    });
    renderPanel(layer, [PART]);
    expect(screen.getByRole('heading', { level: 4, name: 'Product' })).toBeInTheDocument();
  });

  it('shows no Product select on any layer when the tag has no parts', () => {
    const layer = baseLayer({
      type: 'product_slot',
      slot_binding: 'product_image',
      props: { kind: 'product_slot', fieldKey: 'product_image' } as TagLayerProps,
    });
    renderPanel(layer, []);
    expect(screen.queryByRole('heading', { level: 4, name: 'Product' })).toBeNull();
  });
});
