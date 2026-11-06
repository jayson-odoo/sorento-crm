/**
 * PRICETAG-ACCESSORIES: the ONE rule that picks and lays out an "Accessories" box, used by the
 * editor canvas, the request preview and the print page (card rules A3, A5-A8, A10).
 *
 * Written test-FIRST: `./accessory-box` does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import {
  ACCESSORY_BOX_PAD_MM,
  accessoriesOf,
  accessoryBoxLayout,
  accessoryHeaderHeight,
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

  it('too many: only whole cards, the rest counted as dropped (A6)', () => {
    const p = props({ direction: 'horizontal', cardWidth_mm: 25, gap_mm: 2 });
    // 3 whole cards need 2*pad + 75 + 4; a box of 85 holds exactly 3 when pad <= 3.
    const out = accessoryBoxLayout(5, p, 2 * ACCESSORY_BOX_PAD_MM + 25 * 3 + 2 * 2 + 1, 40);
    expect(out).toMatchObject({ shown: 3, dropped: 2 });
    expect(out.cards).toHaveLength(3);
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
