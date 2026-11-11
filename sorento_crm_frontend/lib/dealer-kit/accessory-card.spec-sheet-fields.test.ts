/**
 * SPEC-SHEET-DESIGNER-PARITY B2: a card shows `brand`, `description`, `spec_sheet_description`
 * and `dimensions` of an accessory, and a spec sheet line binding's `accessories` reach
 * `accessoriesOf` unchanged. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import { accessoriesOf } from './accessory-box';
import { cardFieldValue } from './accessory-card';
import type { CardField, LineTagData, TagAccessory, TagBindingData } from './tag-template-types';

const ITEM = {
  kind: 'product',
  id: 'p1',
  code: 'WC-100',
  name: 'Wall hung WC',
  brand: 'Acme',
  description: 'Plain description',
  spec_sheet_description: 'Sheet description',
  dimensions: '800 x 500 x 220 mm',
  spec: null,
  image: null,
  spec_lines: ['One'],
} as unknown as TagAccessory;

describe('cardFieldValue: the new accessory fields', () => {
  it.each([
    ['brand', 'Acme'],
    ['description', 'Plain description'],
    ['spec_sheet_description', 'Sheet description'],
    ['dimensions', '800 x 500 x 220 mm'],
  ])('reads %s', (field, expected) => {
    expect(cardFieldValue(ITEM, field as CardField)).toBe(expected);
  });

  it('reads null when the item has none', () => {
    const bare = { kind: 'product', id: 'p2', name: 'Bare', spec: null, image: null } as TagAccessory;
    for (const field of ['brand', 'description', 'spec_sheet_description', 'dimensions']) {
      expect(cardFieldValue(bare, field as CardField)).toBeNull();
    }
  });
});

describe('accessoriesOf on a spec sheet line binding', () => {
  it('returns the page accessories, product kind with brand and spec sheet description', () => {
    const data = {
      kind: 'line',
      line: { accessories: [ITEM], parts: [] } as unknown as LineTagData,
    } as TagBindingData;
    const items = accessoriesOf(data, undefined);
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      kind: 'product',
      brand: 'Acme',
      spec_sheet_description: 'Sheet description',
    });
  });
});
