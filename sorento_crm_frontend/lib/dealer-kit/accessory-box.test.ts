/**
 * PRICETAG-ACCESSORIES: the ONE rule that picks and lays out an "Accessories" box, used by the
 * editor canvas, the request preview and the print page (card rules A3, A5-A8, A10).
 *
 * Written test-FIRST: `./accessory-box` does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import {
  ACCESSORY_BOX_PAD_MM,
  ACCESSORY_MIN_CARD_WIDTH_MM,
  accessoriesOf,
  accessoryBoxLayout,
  ACCESSORY_DEFAULT_BOX_MM,
  accessoryCardInner,
  accessoryCardLines,
  estimateHeaderWidth,
  accessoryHeaderHeight,
  accessoryLineCount,
  sampleAccessories,
} from './accessory-box';
import {
  defaultAccessoriesProps,
  type AccessoriesLayerProps,
  type LineTagData,
  type ProductTagData,
  type TagAccessory,
  type TagBindingData,
} from './tag-template-types';

const DRAINER: TagAccessory = {
  id: 'a1',
  name: 'DRAINER',
  spec: '390x300x140, Depth: 160mm',
  image: { attachment_id: 'att1', url: 'https://cdn.test/drainer.jpg' },
};
const PULLOUT: TagAccessory = { id: 'a2', name: 'PULL OUT DRAINER', spec: null, image: null };
const BOARD: TagAccessory = { id: 'a3', name: 'CHOPPING BOARD', spec: null, image: null };

function props(over: Partial<AccessoriesLayerProps> = {}): AccessoriesLayerProps {
  return { ...defaultAccessoriesProps(), ...over };
}

function product(over: Partial<ProductTagData> = {}): ProductTagData {
  return {
    id: 'p1',
    code: 'SRTKS7061-BL',
    name: 'SRTKS7061-BL',
    dimensions: '',
    spec_lines: [],
    specs: [],
    images: [],
    list_price: null,
    offer_price: null,
    promotion_id: null,
    barcode: null,
    ...over,
  };
}

function line(over: Partial<LineTagData> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      code: 'SRTKS7061-BL',
      name: 'SRTKS7061-BL',
      dimensions: '',
      spec_lines: '',
      specs: [],
      images: [],
      parts: [],
      open_groups: [],
      set_members: '',
      list_price: null,
      sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      ...over,
    } as LineTagData,
  };
}

// ---------------------------------------------------------------------------
// accessoriesOf (A3)
// ---------------------------------------------------------------------------

describe('accessoriesOf', () => {
  const layer = { props: props() };

  it('reads a request line its resolved list, in order', () => {
    expect(accessoriesOf(line({ accessories: [DRAINER, PULLOUT] }), layer)).toEqual([
      DRAINER,
      PULLOUT,
    ]);
  });

  it('reads nothing from a line pinned before accessories existed', () => {
    expect(accessoriesOf(line({ included_accessories: 'Old text' }), layer)).toEqual([]);
  });

  it('a previewed product with a combo shows the COMBO list, never the product one', () => {
    const data: TagBindingData = {
      kind: 'product',
      product: product({
        accessories: [BOARD],
        combo: {
          id: 'c1',
          name: 'Kitchen sink with 1 tap',
          description: null,
          free_items: 'DRAINER, PULL OUT DRAINER',
          choices: [],
          upgrades: [],
          accessories: [DRAINER, PULLOUT],
        },
      }),
    };
    expect(accessoriesOf(data, layer)).toEqual([DRAINER, PULLOUT]);
  });

  it('a combo with an empty list shows nothing even when the product has one', () => {
    const data: TagBindingData = {
      kind: 'product',
      product: product({
        accessories: [BOARD],
        combo: {
          id: 'c1',
          name: 'x',
          description: null,
          free_items: '',
          choices: [],
          upgrades: [],
          accessories: [],
        },
      }),
    };
    expect(accessoriesOf(data, layer)).toEqual([]);
  });

  it('an ala carte product shows its own list', () => {
    expect(accessoriesOf({ kind: 'product', product: product({ accessories: [BOARD] }) }, layer)).toEqual([
      BOARD,
    ]);
  });

  it('a layer pointed at a combo position reads that product its own list', () => {
    const data = line({
      accessories: [DRAINER],
      slots: {
        main: null,
        fixed: [{ code: 'TAP1', name: 'TAP1', dimensions: '', accessories: [BOARD] }],
        groups: [],
        upgrades: [],
      },
    });
    const pointed = { props: props({ subjectSlot: { kind: 'fixed', index: 0 } }) };
    expect(accessoriesOf(data, pointed)).toEqual([BOARD]);
  });

  it('nothing bound reads nothing', () => {
    expect(accessoriesOf(null, layer)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// accessoryBoxLayout (A5, A6, A7)
// ---------------------------------------------------------------------------

describe('accessoryBoxLayout', () => {
  it('no accessories: nothing at all, not even the frame (A7)', () => {
    const out = accessoryBoxLayout(0, props(), 40, 60);
    expect(out).toMatchObject({ shown: 0, dropped: 0, boxWidth_mm: 0, boxHeight_mm: 0 });
    expect(out.cards).toEqual([]);
  });

  it('vertical: cards stack under the header, full inner width, gap between (A5)', () => {
    const p = props({ direction: 'vertical', gap_mm: 2 });
    const out = accessoryBoxLayout(2, p, 40, 80);
    const header = accessoryHeaderHeight(p);
    expect(out.shown).toBe(2);
    expect(out.cards[0].x_mm).toBeCloseTo(ACCESSORY_BOX_PAD_MM);
    expect(out.cards[0].y_mm).toBeCloseTo(ACCESSORY_BOX_PAD_MM + header);
    expect(out.cards[0].width_mm).toBeCloseTo(40 - 2 * ACCESSORY_BOX_PAD_MM);
    expect(out.cards[1].y_mm).toBeCloseTo(out.cards[0].y_mm + out.cards[0].height_mm + 2);
  });

  it('vertical: the box closes up from the bottom, width unchanged (A5)', () => {
    const out = accessoryBoxLayout(2, props({ direction: 'vertical' }), 40, 80);
    const last = out.cards[1];
    expect(out.boxWidth_mm).toBe(40);
    expect(out.boxHeight_mm).toBeCloseTo(last.y_mm + last.height_mm + ACCESSORY_BOX_PAD_MM);
    expect(out.boxHeight_mm).toBeLessThan(80);
  });

  it('horizontal: cards run left to right at the box card width, box closes up from the right', () => {
    const p = props({ direction: 'horizontal', cardWidth_mm: 25, gap_mm: 2 });
    const out = accessoryBoxLayout(2, p, 100, 40);
    expect(out.shown).toBe(2);
    expect(out.cards.map((c) => c.width_mm)).toEqual([25, 25]);
    expect(out.cards[1].x_mm).toBeCloseTo(out.cards[0].x_mm + 25 + 2);
    expect(out.cards[0].y_mm).toBeCloseTo(out.cards[1].y_mm);
    expect(out.boxWidth_mm).toBeCloseTo(ACCESSORY_BOX_PAD_MM * 2 + 25 * 2 + 2);
    expect(out.boxHeight_mm).toBe(40);
  });

  it('too many: only whole cards, never narrower than the minimum, the rest dropped (A6)', () => {
    const p = props({ direction: 'horizontal', cardWidth_mm: 25, gap_mm: 2 });
    // At the minimum card width, 3 cards need 2*pad + 3*min + 2*gap; one mm more still holds 3.
    const width = 2 * ACCESSORY_BOX_PAD_MM + 3 * ACCESSORY_MIN_CARD_WIDTH_MM + 2 * 2 + 1;
    const out = accessoryBoxLayout(5, p, width, 40);
    expect(out).toMatchObject({ shown: 3, dropped: 2 });
    expect(out.cards).toHaveLength(3);
    for (const card of out.cards) expect(card.width_mm).toBeGreaterThanOrEqual(ACCESSORY_MIN_CARD_WIDTH_MM);
    for (const card of out.cards) {
      expect(card.x_mm + card.width_mm).toBeLessThanOrEqual(out.boxWidth_mm + 1e-9);
    }
  });

  it('vertical too many: dropped from the bottom', () => {
    const p = props({ direction: 'vertical' });
    const one = accessoryBoxLayout(1, p, 40, 200).boxHeight_mm;
    const out = accessoryBoxLayout(5, p, 40, one + 1);
    expect(out).toMatchObject({ shown: 1, dropped: 4 });
  });

  it('a box too small for even one card shows nothing and drops all', () => {
    const out = accessoryBoxLayout(2, props({ direction: 'vertical' }), 40, 3);
    expect(out).toMatchObject({ shown: 0, dropped: 2, boxWidth_mm: 0, boxHeight_mm: 0 });
  });

  it('an empty header takes no height', () => {
    expect(accessoryHeaderHeight(props({ headerText: '   ' }))).toBe(0);
    expect(accessoryHeaderHeight(props({ headerText: 'FREE' }))).toBeGreaterThan(0);
  });
});

describe('sampleAccessories', () => {
  it('gives the designer two named sample cards to style (A7)', () => {
    const samples = sampleAccessories();
    expect(samples).toHaveLength(2);
    expect(samples.every((s) => s.name && s.image === null)).toBe(true);
  });
});

describe('defaultAccessoriesProps', () => {
  it('defaults to a vertical box headed ACCESSORIES INCLUDED with the badge on', () => {
    expect(defaultAccessoriesProps()).toMatchObject({
      kind: 'accessories',
      direction: 'vertical',
      headerText: 'ACCESSORIES INCLUDED',
      showBadge: true,
    });
  });
});

// ---------------------------------------------------------------------------
// Product entries (owner, 6 Nov ~10:45: FREE SRTW5000 on combo SRTWB7065)
// ---------------------------------------------------------------------------

const WASTE: TagAccessory = {
  kind: 'product',
  id: 'p-waste',
  name: 'Popup Waste 80mm (w/o Overflow) Brass',
  spec: null,
  image: { attachment_id: 'att-w', url: 'https://cdn.test/waste.jpg' },
  code: 'SRTW5000',
  list_price: 68,
};

describe('accessoryCardLines', () => {
  it('a library accessory prints its name then its spec', () => {
    expect(accessoryCardLines(DRAINER)).toEqual(['DRAINER', '390x300x140, Depth: 160mm']);
  });

  it('an accessory with no spec prints its name alone', () => {
    expect(accessoryCardLines(PULLOUT)).toEqual(['PULL OUT DRAINER']);
  });

  it('a product prints code, description and LP', () => {
    expect(accessoryCardLines(WASTE)).toEqual([
      'SRTW5000',
      'Popup Waste 80mm (w/o Overflow) Brass',
      'LP: RM 68',
    ]);
  });

  it('a product with no list price leaves the LP line out', () => {
    expect(accessoryCardLines({ ...WASTE, list_price: null })).toEqual([
      'SRTW5000',
      'Popup Waste 80mm (w/o Overflow) Brass',
    ]);
  });
});

describe('accessoryLineCount', () => {
  it('is 2 for accessories only and 3 once a product is listed, so every card matches', () => {
    expect(accessoryLineCount([DRAINER, PULLOUT])).toBe(2);
    expect(accessoryLineCount([DRAINER, WASTE])).toBe(3);
  });
});

describe('three-line cards', () => {
  it('are taller than two-line ones, in both directions', () => {
    for (const direction of ['vertical', 'horizontal'] as const) {
      const p = props({ direction, imageSize_mm: 4 });
      const two = accessoryBoxLayout(1, p, 60, 60, 2).cards[0];
      const three = accessoryBoxLayout(1, p, 60, 60, 3).cards[0];
      expect(three.height_mm).toBeGreaterThan(two.height_mm);
    }
  });

  it('place a third line under the second', () => {
    const p = props({ direction: 'vertical' });
    const card = accessoryBoxLayout(1, p, 60, 60, 3).cards[0];
    const inner = accessoryCardInner(card, p, true, 3);
    expect(inner.lines).toHaveLength(3);
    expect(inner.lines[1].y_mm).toBeGreaterThan(inner.lines[0].y_mm);
    expect(inner.lines[2].y_mm).toBeGreaterThan(inner.lines[1].y_mm);
  });
});

describe('accessoriesOf, a request line part picked (review B1)', () => {
  it('reads that part its own list, and -1 the main product its own', () => {
    const data = line({
      accessories: [DRAINER],
      parts: [{ code: 'TAP1', name: 'TAP1', dimensions: '', accessories: [BOARD] }],
      slots: { main: { code: 'H', name: 'H', dimensions: '', accessories: [PULLOUT] }, fixed: [], groups: [], upgrades: [] },
    });
    expect(accessoriesOf(data, { props: props({ subjectPart: 0 }) })).toEqual([BOARD]);
    expect(accessoriesOf(data, { props: props({ subjectPart: -1 }) })).toEqual([PULLOUT]);
    expect(accessoriesOf(data, { props: props() })).toEqual([DRAINER]);
  });
});

describe('header beside the "+" badge (crew pass 6 Nov: "CCESSORIES INCLUDED" at 45 mm)', () => {
  it('the header starts after the badge and stays centred in the box', () => {
    const out = accessoryBoxLayout(1, props({ showBadge: true }), 45, 60);
    const badgeRight = out.badge!.x_mm + out.badge!.width_mm;
    expect(out.header!.x_mm).toBeGreaterThan(badgeRight);
    const rightGap = out.boxWidth_mm - (out.header!.x_mm + out.header!.width_mm);
    expect(rightGap).toBeCloseTo(out.header!.x_mm);
  });

  it('with the badge off the header uses the full inner width', () => {
    const out = accessoryBoxLayout(1, props({ showBadge: false }), 45, 60);
    expect(out.header!.x_mm).toBeCloseTo(ACCESSORY_BOX_PAD_MM);
    expect(out.header!.width_mm).toBeCloseTo(45 - 2 * ACCESSORY_BOX_PAD_MM);
  });
});

// ---------------------------------------------------------------------------
// Crew pass 2 (6 Nov): defaults fit the owner's examples; the header never truncates
// ---------------------------------------------------------------------------

const ENTRY = (n: number): TagAccessory => ({ id: `e${n}`, name: `ITEM ${n}`, spec: 'Spec line', image: null });
const PRODUCT_ENTRY: TagAccessory = {
  kind: 'product', id: 'p', name: 'Popup Waste 80mm (w/o Overflow) Brass', spec: null, image: null, code: 'SRTW5000', list_price: 68,
};

describe('the default box', () => {
  it('fits 3 vertical cards, also with a product entry (3-line cards)', () => {
    const p = props({ direction: 'vertical' });
    const { width_mm, height_mm } = ACCESSORY_DEFAULT_BOX_MM;
    expect(accessoryBoxLayout(3, p, width_mm, height_mm, 2)).toMatchObject({ shown: 3, dropped: 0 });
    const mixed = [ENTRY(1), ENTRY(2), PRODUCT_ENTRY];
    expect(
      accessoryBoxLayout(3, p, width_mm, height_mm, accessoryLineCount(mixed)),
    ).toMatchObject({ shown: 3, dropped: 0 });
  });

  it('fits 3 horizontal cards (the 2-tap row and more), cards narrowing to fit', () => {
    const p = props({ direction: 'horizontal' });
    const { width_mm, height_mm } = ACCESSORY_DEFAULT_BOX_MM;
    expect(accessoryBoxLayout(2, p, width_mm, height_mm, 2)).toMatchObject({ shown: 2, dropped: 0 });
    const three = accessoryBoxLayout(3, p, width_mm, height_mm, 3);
    expect(three).toMatchObject({ shown: 3, dropped: 0 });
    expect(three.boxWidth_mm).toBeLessThanOrEqual(width_mm + 1e-9);
  });

  it('a narrow horizontal box keeps the set card width when it fits', () => {
    const out = accessoryBoxLayout(2, props({ direction: 'horizontal', cardWidth_mm: 26 }), 200, 40);
    expect(out.cards.map((c) => c.width_mm)).toEqual([26, 26]);
  });
});

describe('the header shrinks, never truncates', () => {
  it('keeps the set size when the text fits', () => {
    const out = accessoryBoxLayout(1, props({ headerText: 'FREE', headerFontSize: 9 }), 60, 60);
    expect(out.header!.fontSize_pt).toBe(9);
  });

  it('shrinks ACCESSORIES INCLUDED to fit a 45 mm box beside the badge', () => {
    const p = props({ headerText: 'ACCESSORIES INCLUDED', headerFontSize: 9, showBadge: true });
    const out = accessoryBoxLayout(1, p, 45, 60);
    expect(out.header!.fontSize_pt).toBeLessThan(9);
    expect(estimateHeaderWidth('ACCESSORIES INCLUDED', out.header!.fontSize_pt)).toBeLessThanOrEqual(
      out.header!.width_mm + 1e-9,
    );
  });
});
