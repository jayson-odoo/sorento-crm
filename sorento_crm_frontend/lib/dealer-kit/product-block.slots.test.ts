/**
 * PRICETAG-COMBO-RENDER K1/K3: `subjectSlot` positions resolve through `subjectOf`.
 *
 * Written test-FIRST. `subjectSlot` is ignored today, so each case is red on the parent
 * product (or on a missing helper) where the position's own product belongs.
 *
 * Decisions where the plan is open:
 * - A binding with no `slots` ignores `subjectSlot` and behaves as today (older pinned rows).
 * - `slotLabel(slot, slots | null)`; `layerSubjectSuffix(layer, parts, slots?)` takes the slots
 *   as a third argument and answers ` - <slot label>`; the main position adds no suffix text
 *   that is asserted here.
 * - Pick and fixed labels are 1-based ("Fixed part 2", "<role>, pick 2").
 */
import { describe, expect, it } from 'vitest';

import {
  layerSubjectSuffix,
  layerText,
  priceBadgeInput,
  resolveSlotText,
  slotImageAttachmentId,
  imagesOf,
  subjectOf,
} from './product-block';
import * as productBlock from './product-block';
import type { LineTagData, ProductTagData, TagBindingData, TagLayer } from './tag-template-types';

type Slot =
  | { kind: 'main' }
  | { kind: 'fixed'; index: number }
  | { kind: 'pick'; group: number; index: number }
  | { kind: 'upgrade'; index: number };

type PartLike = Record<string, unknown> & { code: string };
interface Slots {
  fixed: PartLike[];
  groups: { role: string; size: number; picks: PartLike[] }[];
  upgrades: PartLike[];
}

function part(code: string, list: number | null, extra: Record<string, unknown> = {}): PartLike {
  return {
    product_id: `id-${code}`,
    code,
    name: `Name ${code}`,
    dimensions: '',
    list_price: list,
    sell_price: null,
    images: [{ attachment_id: `att-${code}`, url: `https://cdn/${code}.jpg`, is_primary: true }],
    price_tag_description: `Tag text ${code}`,
    currency: 'MYR',
    ...extra,
  };
}

const HOST = 'SRTKS7061';

function lineWith(slots: Slots | null | undefined, extra: Record<string, unknown> = {}): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 't1',
      line_id: 'l1',
      tag_label: '1a',
      open_groups: [],
      parts: [],
      code: HOST,
      name: 'Host',
      dimensions: '',
      spec_lines: '',
      specs: [],
      set_members: '',
      images: [{ attachment_id: 'att-host', url: 'https://cdn/host.jpg', is_primary: true }],
      list_price: 9999,
      sell_price: null,
      parent_list_price: 2000,
      parent_sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      ...(slots === undefined ? {} : { slots }),
      ...extra,
    } as unknown as LineTagData,
  };
}

function previewWith(slots: Slots | null): TagBindingData {
  return {
    kind: 'product',
    product: {
      id: 'host-id',
      code: HOST,
      name: 'Host',
      dimensions: '',
      spec_lines: [],
      specs: [],
      images: [{ attachment_id: 'att-host', url: 'https://cdn/host.jpg', is_primary: true }],
      list_price: 2000,
      offer_price: null,
      promotion_id: null,
      barcode: null,
      slots,
    } as unknown as ProductTagData,
  };
}

function layer(slot: Slot | undefined, kind: 'text' | 'image' | 'price_badge' = 'text', extra = {}): TagLayer {
  return {
    id: 'x',
    type: kind,
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: kind === 'image' ? 'product_image' : 'code',
    text_override: null,
    props: { kind, text: '', ...(slot ? { subjectSlot: slot } : {}), ...extra },
  } as unknown as TagLayer;
}

const code = (data: TagBindingData | null | undefined, l: TagLayer) => {
  const subject = subjectOf(data, l);
  expect(subject?.kind).toBe('product');
  return subject?.kind === 'product' ? subject.product : null;
};

// The five shapes of the reference flyer ------------------------------------------------

const S1: Slots = {
  fixed: [],
  groups: [
    {
      role: 'Kitchen tap',
      size: 5,
      picks: [part('SRTKT1863SS', 200), part('SRTKT1862SS', 100), part('SRTKT1871SS', 300)],
    },
  ],
  upgrades: [part('SRTKT71SS', 600, { chosen: false })],
};
const S2: Slots = { fixed: [part('SRTWT7449-BL', 150)], groups: [], upgrades: [] };
const S3: Slots = {
  fixed: [],
  groups: [
    { role: 'Tap colour', size: 2, picks: [part('SRTWT7449-BL', 150), part('SRTWT7449-RG', 160)] },
  ],
  upgrades: [],
};
const S4: Slots = {
  fixed: [part('SRTMCB8083-BL', 400), part('SRTWT6203-GM', 500)],
  groups: [],
  upgrades: [],
};
const S5: Slots = { ...S1, upgrades: [part('SRTKT71SS', 600, { chosen: true })] };

describe('main', () => {
  it.each([
    ['S1', S1],
    ['S2', S2],
    ['S3', S3],
    ['S4', S4],
    ['S5', S5],
  ])('%s: reads the main product on a line', (_n, slots) => {
    const product = code(lineWith(slots), layer({ kind: 'main' }));
    expect(product?.code).toBe(HOST);
    expect(product?.list_price).toBe(2000);
  });

  it('reads the product itself on a preview binding', () => {
    expect(code(previewWith(S1), layer({ kind: 'main' }))?.code).toBe(HOST);
  });
});

describe('pick', () => {
  it('S1: picks come back in pick order with their own data', () => {
    const data = lineWith(S1);
    expect(code(data, layer({ kind: 'pick', group: 0, index: 0 }))?.code).toBe('SRTKT1863SS');
    expect(code(data, layer({ kind: 'pick', group: 0, index: 1 }))?.code).toBe('SRTKT1862SS');
    const third = code(data, layer({ kind: 'pick', group: 0, index: 2 }));
    expect(third?.code).toBe('SRTKT1871SS');
    expect(third?.list_price).toBe(300);
    expect(third?.price_tag_description).toBe('Tag text SRTKT1871SS');
  });

  it('S1: a pick the line has not filled is an empty product, never the main product', () => {
    const product = code(lineWith(S1), layer({ kind: 'pick', group: 0, index: 3 }));
    expect(product?.code).toBe('');
    expect(product?.images).toEqual([]);
    expect(product?.list_price).toBeNull();
    expect(product?.offer_price).toBeNull();
  });

  it('S3: two finishes, the third position is empty', () => {
    const data = lineWith(S3);
    expect(code(data, layer({ kind: 'pick', group: 0, index: 0 }))?.code).toBe('SRTWT7449-BL');
    expect(code(data, layer({ kind: 'pick', group: 0, index: 1 }))?.code).toBe('SRTWT7449-RG');
    expect(code(data, layer({ kind: 'pick', group: 0, index: 2 }))?.code).toBe('');
  });

  it('a group the combo does not have is empty', () => {
    expect(code(lineWith(S3), layer({ kind: 'pick', group: 1, index: 0 }))?.code).toBe('');
    expect(code(lineWith(S2), layer({ kind: 'pick', group: 0, index: 0 }))?.code).toBe('');
  });

  it('reads the same position on a preview binding', () => {
    expect(code(previewWith(S1), layer({ kind: 'pick', group: 0, index: 1 }))?.code).toBe('SRTKT1862SS');
    expect(code(previewWith(S1), layer({ kind: 'pick', group: 0, index: 4 }))?.code).toBe('');
  });
});

describe('fixed', () => {
  it('S2: the one fixed part, and nothing at the next position', () => {
    const data = lineWith(S2);
    expect(code(data, layer({ kind: 'fixed', index: 0 }))?.code).toBe('SRTWT7449-BL');
    expect(code(data, layer({ kind: 'fixed', index: 1 }))?.code).toBe('');
  });

  it('S4: two fixed parts in order, the third is empty', () => {
    const data = lineWith(S4);
    expect(code(data, layer({ kind: 'fixed', index: 0 }))?.code).toBe('SRTMCB8083-BL');
    expect(code(data, layer({ kind: 'fixed', index: 1 }))?.code).toBe('SRTWT6203-GM');
    expect(code(data, layer({ kind: 'fixed', index: 2 }))?.code).toBe('');
  });
});

describe('upgrade', () => {
  it('S1 and S5: the combo upgrade, with its own list price', () => {
    for (const slots of [S1, S5]) {
      const product = code(lineWith(slots), layer({ kind: 'upgrade', index: 0 }));
      expect(product?.code).toBe('SRTKT71SS');
      expect(product?.list_price).toBe(600);
    }
  });

  it('a second upgrade is empty, and so is any upgrade on a combo without one', () => {
    expect(code(lineWith(S5), layer({ kind: 'upgrade', index: 1 }))?.code).toBe('');
    expect(code(lineWith(S4), layer({ kind: 'upgrade', index: 0 }))?.code).toBe('');
  });
});

describe('what a position prints', () => {
  it('resolveSlotText reads the position product, and nothing falls back to the main product', () => {
    const l = layer({ kind: 'pick', group: 0, index: 1 });
    expect(resolveSlotText(l as never, lineWith(S1))).toBe('SRTKT1862SS');
    const missing = layer({ kind: 'pick', group: 0, index: 4 });
    expect(resolveSlotText(missing as never, lineWith(S1)) || '').toBe('');
    expect(layerText(missing, lineWith(S1))).not.toContain(HOST);
  });

  it('slotImageAttachmentId gives the position product picture, null when empty', () => {
    const l = layer({ kind: 'pick', group: 0, index: 1 }, 'image');
    const data = lineWith(S1);
    expect(slotImageAttachmentId(l, imagesOf(subjectOf(data, l)))).toBe('att-SRTKT1862SS');
    const missing = layer({ kind: 'pick', group: 0, index: 4 }, 'image');
    expect(slotImageAttachmentId(missing, imagesOf(subjectOf(data, missing)))).toBeNull();
  });

  it('a price badge reads the position own list price, empty for a missing position', () => {
    const badge = layer({ kind: 'upgrade', index: 0 }, 'price_badge');
    expect(priceBadgeInput(lineWith(S1), badge).listPrice).toBe(600);
    const missing = layer({ kind: 'fixed', index: 3 }, 'price_badge');
    expect(priceBadgeInput(lineWith(S4), missing)).toEqual({ listPrice: null, offerPrice: null });
  });

  it('a main price badge reads the main product alone', () => {
    const badge = layer({ kind: 'main' }, 'price_badge');
    expect(priceBadgeInput(lineWith(S3), badge).listPrice).toBe(2000);
  });
});

describe('layers without a position', () => {
  it('print exactly as today: the binding passes through untouched', () => {
    const data = lineWith(S1);
    expect(subjectOf(data, layer(undefined))).toBe(data);
  });

  it('subjectPart still works when there is no subjectSlot', () => {
    const data = lineWith(S1, { parts: [part('SRTOLD1', 10)] });
    const l = layer(undefined, 'text', { subjectPart: 0 });
    expect(code(data, l)?.code).toBe('SRTOLD1');
  });

  it('subjectSlot wins over subjectPart', () => {
    const data = lineWith(S1, { parts: [part('SRTOLD1', 10)] });
    const l = layer({ kind: 'pick', group: 0, index: 0 }, 'text', { subjectPart: 0 });
    expect(code(data, l)?.code).toBe('SRTKT1863SS');
  });

  it('a binding that carries no slots ignores subjectSlot (older rows)', () => {
    const data = lineWith(undefined);
    expect(subjectOf(data, layer({ kind: 'pick', group: 0, index: 0 }))).toBe(data);
    const nullSlots = lineWith(null);
    expect(subjectOf(nullSlots, layer({ kind: 'pick', group: 0, index: 0 }))).toBe(nullSlots);
  });
});

describe('slotLabel and the Layers panel suffix', () => {
  const slotLabel = (productBlock as unknown as {
    slotLabel: (slot: Slot, slots: Slots | null) => string;
  }).slotLabel;

  it('names each position generically with nothing previewed', () => {
    expect(slotLabel({ kind: 'main' }, null)).toBe('Main product');
    expect(slotLabel({ kind: 'fixed', index: 1 }, null)).toBe('Fixed part 2');
    expect(slotLabel({ kind: 'pick', group: 0, index: 1 }, null)).toBe('Choice group 1, pick 2');
    expect(slotLabel({ kind: 'pick', group: 2, index: 0 }, null)).toBe('Choice group 3, pick 1');
    expect(slotLabel({ kind: 'upgrade', index: 0 }, null)).toBe('Upgrade 1');
  });

  it('uses the previewed combo group name', () => {
    expect(slotLabel({ kind: 'pick', group: 0, index: 1 }, S1)).toBe('Kitchen tap, pick 2');
    expect(slotLabel({ kind: 'pick', group: 0, index: 0 }, S3)).toBe('Tap colour, pick 1');
  });

  it('falls back to the generic group name for a group the combo lacks', () => {
    expect(slotLabel({ kind: 'pick', group: 1, index: 0 }, S3)).toBe('Choice group 2, pick 1');
  });

  it('the suffix names the position', () => {
    const suffix = layerSubjectSuffix as unknown as (l: TagLayer, p: unknown, s?: Slots | null) => string;
    expect(suffix(layer({ kind: 'pick', group: 0, index: 1 }), undefined, S1)).toBe(' - Kitchen tap, pick 2');
    expect(suffix(layer({ kind: 'pick', group: 0, index: 1 }), undefined, null)).toBe(
      ' - Choice group 1, pick 2',
    );
    expect(suffix(layer({ kind: 'fixed', index: 0 }), undefined, S4)).toBe(' - Fixed part 1');
    expect(suffix(layer({ kind: 'upgrade', index: 0 }), undefined, S1)).toBe(' - Upgrade 1');
  });

  it('a layer with only subjectPart keeps the code suffix', () => {
    const l = layer(undefined, 'text', { subjectPart: 0 });
    expect(layerSubjectSuffix(l, [part('SRTOLD1', 1)] as never)).toBe(' - SRTOLD1');
  });
});
