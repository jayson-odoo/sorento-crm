/**
 * PRICETAG-LPSP S6, AC-18: the `price` and `price_label` slot bindings.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). Neither binding resolves yet (`resolveSlotText`
 * answers null for an unknown binding), so each case is red on a null where a figure or label
 * belongs.
 *
 * `price` = the line's SP when the line shows SP, else its LP, printed as a bare figure like the
 * `list_price` / `sell_price` text slots. `price_label` = "SP" / "LP" for the figure `price` prints.
 * An SP line with no SP to show prints LP, so its label says LP (the card: "prints LP").
 */
import { describe, expect, it } from 'vitest';

import type {
  LineTagData,
  ProductTagData,
  TagBindingData,
} from './tag-template-types';
import { resolveSlotText } from './product-block';

const PRICE = { slot_binding: 'price' } as never;
const LABEL = { slot_binding: 'price_label' } as never;

function line(overrides: Partial<LineTagData> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 'tag-1',
      line_id: 'line-1',
      tag_label: '1a',
      open_groups: [],
      parts: [],
      code: 'CAB-01',
      name: 'Cabinet',
      dimensions: '',
      spec_lines: '',
      specs: [],
      set_members: '',
      images: [],
      list_price: 1698,
      sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      ...overrides,
    } as LineTagData,
  };
}

function bareProduct(overrides: Partial<ProductTagData> = {}): TagBindingData {
  return {
    kind: 'product',
    product: {
      id: 'p1',
      code: 'SK-1',
      name: 'Sink',
      dimensions: '',
      spec_lines: [],
      specs: [],
      images: [],
      list_price: 1599,
      offer_price: null,
      promotion_id: null,
      barcode: null,
      ...overrides,
    } as ProductTagData,
  };
}

describe('resolveSlotText price slots (AC-18)', () => {
  it('price is the SP figure on an SP line', () => {
    const data = line({ list_price: 1698, sell_price: 1500, show_promo_price: true });
    expect(resolveSlotText(PRICE, data)).toBe('1,500');
    expect(resolveSlotText(LABEL, data)).toBe('SP');
  });

  it('price is the LP figure on an LP line', () => {
    const data = line({ list_price: 1698, sell_price: null, show_promo_price: false });
    expect(resolveSlotText(PRICE, data)).toBe('1,698');
    expect(resolveSlotText(LABEL, data)).toBe('LP');
  });

  it('an LP line never prints its selling figure, even when one is carried', () => {
    const data = line({ list_price: 1698, sell_price: 1500, show_promo_price: false });
    expect(resolveSlotText(PRICE, data)).toBe('1,698');
    expect(resolveSlotText(LABEL, data)).toBe('LP');
  });

  it('an SP line with no SP to show prints the LP figure and says LP', () => {
    const data = line({ list_price: 1698, sell_price: null, show_promo_price: true });
    expect(resolveSlotText(PRICE, data)).toBe('1,698');
    expect(resolveSlotText(LABEL, data)).toBe('LP');
  });

  it('price is a bare figure, no RM prefix, like the other text price slots', () => {
    const data = line({ list_price: 1698, sell_price: 599, show_promo_price: true });
    expect(resolveSlotText(PRICE, data)).toBe('599');
    expect(resolveSlotText(PRICE, data)).not.toMatch(/RM/);
  });

  it('a designer preview product with an offer reads as SP, without one as LP', () => {
    expect(resolveSlotText(PRICE, bareProduct({ list_price: 1599, offer_price: 535 }))).toBe('535');
    expect(resolveSlotText(LABEL, bareProduct({ list_price: 1599, offer_price: 535 }))).toBe('SP');
    expect(resolveSlotText(PRICE, bareProduct({ list_price: 1599, offer_price: null }))).toBe('1,599');
    expect(resolveSlotText(LABEL, bareProduct({ list_price: 1599, offer_price: null }))).toBe('LP');
  });

  it('is null (the layer keeps its own text) when there is no data yet', () => {
    expect(resolveSlotText(PRICE, null)).toBeNull();
    expect(resolveSlotText(LABEL, undefined)).toBeNull();
  });

  it('list_price and sell_price keep their own meaning on the same line', () => {
    const data = line({ list_price: 1698, sell_price: 1500, show_promo_price: true });
    expect(resolveSlotText({ slot_binding: 'list_price' } as never, data)).toBe('1,698');
    expect(resolveSlotText({ slot_binding: 'sell_price' } as never, data)).toBe('1,500');
  });
});
