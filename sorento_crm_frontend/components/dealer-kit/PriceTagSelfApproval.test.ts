/**
 * PRICETAG-SELF-APPROVAL R2/R3: the sheet he approves is built from the request's
 * REAL tags, so every placement the server checks belongs to this request.
 */
import { describe, expect, it } from 'vitest';

import { buildSelfProof, requestTags } from './PriceTagSelfApproval';
import type { PriceTagRequestLine } from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';

function line(id: string, tags: { id: string; quantity: number }[]): PriceTagRequestLine {
  return {
    id,
    line_type: 'product',
    product_id: `product-${id}`,
    product_set_id: null,
    name: 'Basin',
    code: 'B-1',
    show_promo_price: false,
    quantity: 1,
    included_accessories: null,
    remarks: null,
    sort_order: 0,
    tags: tags.map((tag, index) => ({ ...tag, label: `1${'abc'[index]}` })),
  };
}

const template: TagTemplate = {
  id: 'tpl-1',
  name: 'Sink tag',
  family: 'ala_carte',
  doc: { layers: [], width_mm: 90, height_mm: 60 },
  print_size: { width_mm: 90, height_mm: 60 },
  created_at: '',
  updated_at: '',
};

const response = (templates: Record<string, TagTemplate>) => ({
  lines: [],
  templates,
  assets: {},
  images: {},
  fonts: [],
});

describe('requestTags', () => {
  it('lists every tag of every line with the line it prints', () => {
    const tags = requestTags([
      line('l1', [{ id: 't1', quantity: 2 }]),
      line('l2', [
        { id: 't2', quantity: 1 },
        { id: 't3', quantity: 1 },
      ]),
    ]);

    expect(tags.map((t) => [t.id, t.line.id, t.quantity])).toEqual([
      ['t1', 'l1', 2],
      ['t2', 'l2', 1],
      ['t3', 'l2', 1],
    ]);
  });

  it('skips a line with no tags', () => {
    expect(requestTags([line('l1', [])])).toEqual([]);
  });
});

describe('buildSelfProof', () => {
  it('places only this request\'s tag ids', () => {
    const built = buildSelfProof(
      [line('l1', [{ id: 't1', quantity: 1 }])],
      response({ l1: template }),
    );

    const placed = built?.doc.sheets.flatMap((sheet) => sheet.tags.map((t) => t.request_tag_id));
    expect(placed?.length).toBeGreaterThan(0);
    expect(new Set(placed)).toEqual(new Set(['t1']));
    expect(built?.doc.kind).toBe('tag_sheet');
  });

  it('is null when no line has a template to draw', () => {
    expect(buildSelfProof([line('l1', [{ id: 't1', quantity: 1 }])], response({}))).toBeNull();
  });
});
