/**
 * PRICETAG-COMBO: the five Combo slots, the three Combo merge tokens, and the
 * template pick for the two starter families.
 *
 * UAC: documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md
 * (AC-4.2 to AC-4.8, AC-8.10).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The slots `combo_image`, `combo_name`,
 * `combo_description`, `combo_choices`, `combo_topups` and the tokens `combo.name`,
 * `combo.description`, `combo.free_items` do not resolve yet, so the cases are red on a
 * `null` where text is expected. Synthetic codes and prices only.
 *
 * The payload shape is the backend's `combo` object (AC-2.1) on the line row (and on the
 * product row of the designer's Preview combo, AC-5.3). `resolveSlotText` and its
 * neighbours are the one resolver the canvas, the preview and the PDF share (AC-4.8).
 */

import { describe, expect, it } from 'vitest';

import {
  defaultTemplateFor,
} from './request-tags';
import { mergeFieldCatalog, renderMergeFields } from './merge-fields';
import {
  layerText,
  imagesOf,
  resolveSlotText,
  slotImageAttachmentId,
  subjectOf,
} from './product-block';
import {
  defaultTextProps,
  type LineTagData,
  type ProductTagData,
  type SlotBinding,
  type TagBindingData,
  type TagLayer,
  type TagTemplate,
  type TagTemplateFamily,
} from './tag-template-types';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

interface ComboOption {
  product_id: string;
  code: string;
  description: string;
  list_price: number | null;
  sell_price: number | null;
  picked: boolean;
}
interface ComboUpgrade {
  product_id: string;
  code: string;
  description: string;
  topup_amount: number | null;
  picked: boolean;
}
interface ComboData {
  id: string;
  name: string;
  description: string | null;
  free_items: string | null;
  choices: { role: string; options: ComboOption[] }[];
  upgrades: ComboUpgrade[];
}

const WHITE: ComboOption = {
  product_id: 'p-white',
  code: 'ZZW',
  description: 'White basin',
  list_price: 300,
  sell_price: 280,
  picked: false,
};
const BLACK: ComboOption = {
  product_id: 'p-black',
  code: 'ZZB',
  description: 'Black basin',
  list_price: 400,
  sell_price: null,
  picked: false,
};
const STONE: ComboUpgrade = {
  product_id: 'p-stone',
  code: 'ZZU',
  description: 'Stone basin',
  topup_amount: 100,
  picked: false,
};

function combo(overrides: Partial<ComboData> = {}): ComboData {
  return {
    id: 'combo-1',
    name: '3 in 1',
    description: 'Cabinet, mirror and basin',
    free_items: 'Tap, waste',
    choices: [{ role: 'Basin', options: [WHITE, BLACK] }],
    upgrades: [STONE],
    ...overrides,
  };
}

const COVER = { attachment_id: 'att-cover', url: 'https://cdn/cover.jpg', is_primary: true };
const OTHER = { attachment_id: 'att-other', url: 'https://cdn/other.jpg', is_primary: false };

function line(extra: Record<string, unknown> = {}): LineTagData {
  return {
    tag_id: 't1',
    line_id: 'l1',
    tag_label: '1a',
    open_groups: [],
    parts: [],
    code: 'ZZHOST-1',
    name: 'ZZHOST-1',
    dimensions: '800 x 500 x 220 mm',
    spec_lines: '',
    specs: [],
    set_members: '',
    images: [COVER, OTHER],
    list_price: 1500,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    barcode: null,
    price_tag_description: null,
    ...extra,
  } as LineTagData;
}

function lineData(extra: Record<string, unknown> = {}): TagBindingData {
  return { kind: 'line', line: line(extra) };
}

function productData(extra: Record<string, unknown> = {}): TagBindingData {
  return {
    kind: 'product',
    product: {
      id: 'p1',
      code: 'ZZHOST-1',
      name: 'ZZHOST-1',
      dimensions: '',
      spec_lines: [],
      specs: [],
      images: [COVER, OTHER],
      list_price: 1000,
      offer_price: null,
      promotion_id: null,
      barcode: null,
      price_tag_description: null,
      ...extra,
    } as ProductTagData,
  };
}

function slotLayer(slot: SlotBinding, props: Record<string, unknown> = {}) {
  return { slot_binding: slot, props: { ...defaultTextProps(), ...props } };
}

function text(slot: SlotBinding, data: TagBindingData | null | undefined) {
  return resolveSlotText(slotLayer(slot), data);
}

function lines(value: string | null): string[] {
  return (value ?? '').split('\n').filter((entry) => entry !== '');
}

// ---------------------------------------------------------------------------
// AC-4.3 Combo Photo
// ---------------------------------------------------------------------------

function imageLayer(slot: SlotBinding, source: unknown = null): Pick<TagLayer, 'slot_binding' | 'props'> {
  return {
    slot_binding: slot,
    props: { kind: 'image', source, fit: 'contain' },
  } as unknown as Pick<TagLayer, 'slot_binding' | 'props'>;
}

function imageIdFor(layer: Pick<TagLayer, 'slot_binding' | 'props'>, data: TagBindingData) {
  return slotImageAttachmentId(layer, imagesOf(subjectOf(data, layer)));
}

describe('Combo Photo (AC-4.3)', () => {
  it('prints the combo cover picture, which leads the line images', () => {
    expect(imageIdFor(imageLayer('combo_image' as SlotBinding), lineData({ combo: combo() }))).toBe(
      'att-cover',
    );
  });

  it('ignores a layer pinned photo source', () => {
    const pinned = { type: 'product_attachment', attachmentId: 'att-other' };
    expect(
      imageIdFor(imageLayer('combo_image' as SlotBinding, pinned), lineData({ combo: combo() })),
    ).toBe('att-cover');
  });

  it('ignores a pinned photo source on a combo with no cover and falls to the primary photo', () => {
    const pinned = { type: 'product_attachment', attachmentId: 'att-other' };
    const noCover = { images: [{ ...OTHER, is_primary: true }, { ...COVER, is_primary: false }] };
    expect(
      imageIdFor(
        imageLayer('combo_image' as SlotBinding, pinned),
        lineData({ combo: combo(), ...noCover }),
      ),
    ).toBe('att-other');
  });

  it('falls to the product primary photo on a line with no combo', () => {
    expect(imageIdFor(imageLayer('combo_image' as SlotBinding), lineData({ combo: null }))).toBe(
      'att-cover',
    );
  });

  it('draws nothing when there is no photo at all', () => {
    expect(
      imageIdFor(imageLayer('combo_image' as SlotBinding), lineData({ combo: null, images: [] })),
    ).toBeNull();
  });

  it('product_image keeps today behaviour: a pinned photo of this product still wins', () => {
    const pinned = { type: 'product_attachment', attachmentId: 'att-other' };
    expect(
      imageIdFor(imageLayer('product_image', pinned), lineData({ combo: combo() })),
    ).toBe('att-other');
  });

  it('works for the designer preview, where the combo rides on the product row', () => {
    const pinned = { type: 'product_attachment', attachmentId: 'att-other' };
    expect(
      imageIdFor(
        imageLayer('combo_image' as SlotBinding, pinned),
        productData({ combo: combo() }),
      ),
    ).toBe('att-cover');
  });
});

// ---------------------------------------------------------------------------
// AC-4.4 Combo Name / Combo Description
// ---------------------------------------------------------------------------

describe('Combo Name (AC-4.4)', () => {
  it('prints the combo name', () => {
    expect(text('combo_name' as SlotBinding, lineData({ combo: combo() }))).toBe('3 in 1');
  });

  it('prints the product code when the line has no combo', () => {
    expect(text('combo_name' as SlotBinding, lineData({ combo: null }))).toBe('ZZHOST-1');
  });

  it('prints the product code from a stale payload that has no combo key at all', () => {
    expect(text('combo_name' as SlotBinding, lineData())).toBe('ZZHOST-1');
  });

  it('reads the combo from the preview product row', () => {
    expect(text('combo_name' as SlotBinding, productData({ combo: combo() }))).toBe('3 in 1');
  });
});

describe('Combo Description (AC-4.4)', () => {
  it('prints the combo description', () => {
    expect(text('combo_description' as SlotBinding, lineData({ combo: combo() }))).toBe(
      'Cabinet, mirror and basin',
    );
  });

  it('falls back to the product price tag description when the combo has none', () => {
    const data = lineData({
      combo: combo({ description: null }),
      price_tag_description: 'Product tag copy',
    });
    expect(text('combo_description' as SlotBinding, data)).toBe('Product tag copy');
  });

  it('falls back to the product price tag description on a line with no combo', () => {
    expect(
      text(
        'combo_description' as SlotBinding,
        lineData({ combo: null, price_tag_description: 'Product tag copy' }),
      ),
    ).toBe('Product tag copy');
  });

  it('prints nothing when neither exists', () => {
    const value = text('combo_description' as SlotBinding, lineData({ combo: combo({ description: null }) }));
    expect(['', null]).toContain(value);
    expect(value).not.toBe('Text');
  });

  it('a stale payload without combo falls back the same way', () => {
    expect(
      text('combo_description' as SlotBinding, lineData({ price_tag_description: 'Product tag copy' })),
    ).toBe('Product tag copy');
  });
});

// ---------------------------------------------------------------------------
// AC-4.5 Combo Choices
// ---------------------------------------------------------------------------

describe('Combo Choices (AC-4.5)', () => {
  it('lists a group as a PICK ONE header and one line per option, price only when the option has its own', () => {
    const value = text('combo_choices' as SlotBinding, lineData({ combo: combo({ upgrades: [] }) }));
    expect(lines(value)).toEqual([
      'BASIN: PICK ONE',
      'ZZW  White basin  RM 280',
      'ZZB  Black basin',
    ]);
  });

  it('prints a group of one option with the role alone as header', () => {
    const data = lineData({
      combo: combo({ upgrades: [], choices: [{ role: 'Tap', options: [{ ...BLACK, code: 'ZZT', description: 'Tap' }] }] }),
    });
    expect(lines(text('combo_choices' as SlotBinding, data))).toEqual(['TAP', 'ZZT  Tap']);
  });

  it('prints groups one after another', () => {
    const data = lineData({
      combo: combo({
        upgrades: [],
        choices: [
          { role: 'Basin', options: [WHITE, BLACK] },
          { role: 'Tap', options: [{ ...BLACK, code: 'ZZT', description: 'Tap', sell_price: 50 }] },
        ],
      }),
    });
    expect(lines(text('combo_choices' as SlotBinding, data))).toEqual([
      'BASIN: PICK ONE',
      'ZZW  White basin  RM 280',
      'ZZB  Black basin',
      'TAP',
      'ZZT  Tap  RM 50',
    ]);
  });

  it('with a pick made, prints only the picked line under the role alone', () => {
    const picked = { ...WHITE, picked: true };
    const data = lineData({
      combo: combo({ upgrades: [], choices: [{ role: 'Basin', options: [picked, BLACK] }] }),
    });
    expect(lines(text('combo_choices' as SlotBinding, data))).toEqual([
      'BASIN',
      'ZZW  White basin  RM 280',
    ]);
  });

  it('a picked option without its own price prints no price', () => {
    const picked = { ...BLACK, picked: true };
    const data = lineData({
      combo: combo({ upgrades: [], choices: [{ role: 'Basin', options: [WHITE, picked] }] }),
    });
    expect(lines(text('combo_choices' as SlotBinding, data))).toEqual(['BASIN', 'ZZB  Black basin']);
  });

  it('a picked upgrade prints as the only line with +RM and its top-up', () => {
    const data = lineData({
      combo: combo({ upgrades: [{ ...STONE, picked: true }] }),
    });
    const printed = lines(text('combo_choices' as SlotBinding, data));
    expect(printed).toContain('ZZU  Stone basin  +RM 100');
    expect(printed).not.toContain('ZZW  White basin  RM 280');
    expect(printed).not.toContain('ZZB  Black basin');
    expect(printed.filter((entry) => entry.startsWith('ZZ'))).toHaveLength(1);
  });

  it('on a combo with several groups a picked upgrade follows in its own UPGRADE section (AC-4.5)', () => {
    const data = lineData({
      combo: combo({
        upgrades: [{ ...STONE, picked: true }],
        choices: [
          { role: 'Basin', options: [WHITE, BLACK] },
          { role: 'Tap', options: [{ ...BLACK, code: 'ZZT', description: 'Tap' }] },
        ],
      }),
    });
    expect(lines(text('combo_choices' as SlotBinding, data))).toEqual([
      'BASIN: PICK ONE',
      'ZZW  White basin  RM 280',
      'ZZB  Black basin',
      'TAP',
      'ZZT  Tap',
      'UPGRADE',
      'ZZU  Stone basin  +RM 100',
    ]);
  });

  it('does not repeat the code a description already ends with', () => {
    const long = { ...WHITE, code: 'ZZWB1-BL', description: 'ZZWB1-BL WASH BASIN ONLY (440x440mm) ZZWB1-BL' };
    const data = lineData({ combo: combo({ upgrades: [], choices: [{ role: 'Basin', options: [long, BLACK] }] }) });
    expect(lines(text('combo_choices' as SlotBinding, data))[1]).toBe('ZZWB1-BL  WASH BASIN ONLY (440x440mm)  RM 280');
  });

  it('a description that is only the code prints the code once, in the top-ups too', () => {
    const only = { ...STONE, code: 'ZZUP1', description: 'ZZUP1', topup_amount: 100 };
    const data = lineData({ combo: combo({ upgrades: [only] }) });
    expect(lines(text('combo_topups' as SlotBinding, data))[1]).toBe('ZZUP1  +RM 100');
  });

  it('a picked upgrade with no top-up prints without an amount', () => {
    const data = lineData({
      combo: combo({ upgrades: [{ ...STONE, topup_amount: null, picked: true }] }),
    });
    const printed = lines(text('combo_choices' as SlotBinding, data));
    expect(printed).toContain('ZZU  Stone basin');
    expect(printed.join('\n')).not.toContain('+RM');
  });

  it('prints an empty string, not null, for a line with no combo, so no placeholder shows (AC-4.7)', () => {
    expect(text('combo_choices' as SlotBinding, lineData({ combo: null }))).toBe('');
  });

  it('prints an empty string for a stale payload with no combo key', () => {
    expect(text('combo_choices' as SlotBinding, lineData())).toBe('');
  });

  it('reads the preview product row too', () => {
    const value = text('combo_choices' as SlotBinding, productData({ combo: combo({ upgrades: [] }) }));
    expect(lines(value)[0]).toBe('BASIN: PICK ONE');
  });
});

// ---------------------------------------------------------------------------
// AC-4.6 Combo Top-ups
// ---------------------------------------------------------------------------

describe('Combo Top-ups (AC-4.6)', () => {
  it('prints an UPGRADE header then one line per upgrade with its amount', () => {
    const second: ComboUpgrade = { ...STONE, product_id: 'p-glass', code: 'ZZG', description: 'Glass basin', topup_amount: null };
    const data = lineData({ combo: combo({ upgrades: [STONE, second] }) });
    expect(lines(text('combo_topups' as SlotBinding, data))).toEqual([
      'UPGRADE',
      'ZZU  Stone basin  +RM 100',
      'ZZG  Glass basin',
    ]);
  });

  it('prints nothing when the combo has no upgrades', () => {
    expect(text('combo_topups' as SlotBinding, lineData({ combo: combo({ upgrades: [] }) }))).toBe('');
  });

  it('prints nothing once an upgrade was picked', () => {
    const data = lineData({ combo: combo({ upgrades: [{ ...STONE, picked: true }] }) });
    expect(text('combo_topups' as SlotBinding, data)).toBe('');
  });

  it('prints an empty string for a line with no combo (AC-4.7)', () => {
    expect(text('combo_topups' as SlotBinding, lineData({ combo: null }))).toBe('');
    expect(text('combo_topups' as SlotBinding, lineData())).toBe('');
  });
});

// ---------------------------------------------------------------------------
// AC-4.2 Combo merge tokens
// ---------------------------------------------------------------------------

describe('Combo merge tokens (AC-4.2)', () => {
  it('resolve in a text layer', () => {
    const data = lineData({ combo: combo() });
    expect(renderMergeFields('{{combo.name}}', data, 'print')).toBe('3 in 1');
    expect(renderMergeFields('{{combo.description}}', data, 'print')).toBe('Cabinet, mirror and basin');
    expect(renderMergeFields('{{combo.free_items}}', data, 'print')).toBe('Tap, waste');
    expect(renderMergeFields('Includes: {{combo.free_items}}.', data, 'print')).toBe(
      'Includes: Tap, waste.',
    );
  });

  it('print nothing on a line with no combo, never the raw token', () => {
    const data = lineData({ combo: null });
    for (const token of ['combo.name', 'combo.description', 'combo.free_items']) {
      expect(renderMergeFields(`{{${token}}}`, data, 'print')).toBe('');
    }
  });

  it('print nothing from a stale payload with no combo key', () => {
    expect(renderMergeFields('{{combo.name}}', lineData(), 'print')).toBe('');
  });

  it('resolve from the preview product row', () => {
    expect(renderMergeFields('{{combo.name}}', productData({ combo: combo() }), 'print')).toBe(
      '3 in 1',
    );
  });

  it('appear in a Combo group of Insert field', () => {
    const catalog = mergeFieldCatalog([]);
    const comboFields = catalog.filter((field) => (field.group as string) === 'Combo');
    expect(comboFields.map((field) => field.path).sort()).toEqual([
      'combo.description',
      'combo.free_items',
      'combo.name',
      'combo.parts',
    ]);
    expect(comboFields.map((field) => field.token).sort()).toEqual([
      '{{combo.description}}',
      '{{combo.free_items}}',
      '{{combo.name}}',
      '{{combo.parts}}',
    ]);
    expect(comboFields.every((field) => field.label && !field.label.includes('combo.'))).toBe(true);
  });

  it('leave the existing fields and their order alone', () => {
    const existing = mergeFieldCatalog([])
      // PS-SPEC-SHEET's group is new, after Combo; the price tag fields before it are unchanged.
      .filter((field) => !['Combo', 'Combo positions', 'Spec sheet'].includes(field.group as string))
      .map((field) => field.path);
    expect(existing).toEqual([
      'product.code',
      'product.name',
      'product.dimensions',
      'product.spec_lines',
      'product.price_tag_description',
      'product.list_price',
      'product.sell_price',
      'product.currency',
      'product.included_accessories',
      'set.code',
      'set.name',
      'set.members',
      'line.quantity',
      'line.parts',
      'line.parts_names',
    ]);
  });

  it('are not offered where only Product and Specs are (the Specifications tab)', () => {
    const narrowed = mergeFieldCatalog([], ['Product', 'Specs']);
    expect(narrowed.some((field) => (field.group as string) === 'Combo')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// AC-0.3 Existing slots resolve as before
// ---------------------------------------------------------------------------

describe('existing slots on a line that carries a combo (AC-0.3)', () => {
  it('code, name and accessories are unchanged', () => {
    const data = lineData({ combo: combo(), included_accessories: 'Tap, waste' });
    expect(text('code', data)).toBe('ZZHOST-1');
    expect(text('included_accessories', data)).toBe('Tap, waste');
    expect(text('set_members', data)).toBe('');
  });
});

// ---------------------------------------------------------------------------
// AC-8.10 Auto pick of the two starter families
// ---------------------------------------------------------------------------

function template(id: string, family: TagTemplateFamily): TagTemplate {
  return {
    id,
    name: `${family} template`,
    family,
    doc: { layers: [], width_mm: 60, height_mm: 40 },
    print_size: { width_mm: 60, height_mm: 40 },
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  } as TagTemplate;
}

const STARTERS: TagTemplate[] = [
  template('t-plain', 'ala_carte'),
  template('t-bf', 'furniture_set'),
  template('t-ks', 'sink_combo'),
];

describe('defaultTemplateFor with the two starter templates (AC-8.10)', () => {
  const productLine = { line_type: 'product' as const };
  const comboLine = { line_type: 'product' as const, combo_id: 'combo-1' };

  it('a combo line on a bf product picks the furniture set starter', () => {
    expect(defaultTemplateFor(comboLine, STARTERS, 'SRTBF99999')?.id).toBe('t-bf');
  });

  it('a line with no combo on a bf product picks the furniture set starter', () => {
    expect(defaultTemplateFor(productLine, STARTERS, 'SRTBF99999')?.id).toBe('t-bf');
  });

  it('a combo line on a ks product picks the sink combo starter', () => {
    expect(defaultTemplateFor(comboLine, STARTERS, 'SRTKS2435')?.id).toBe('t-ks');
  });

  it('a line with no combo on a ks product picks the sink combo starter', () => {
    expect(defaultTemplateFor(productLine, STARTERS, 'SRTKS2435')?.id).toBe('t-ks');
  });

  it('a combo line never falls to the first ala carte template when its family exists', () => {
    const shuffled = [STARTERS[0], STARTERS[2], STARTERS[1]];
    expect(defaultTemplateFor(comboLine, shuffled, 'SRTBF99999')?.id).toBe('t-bf');
  });
});


// ---------------------------------------------------------------------------
// A blank price or blank free items print nothing (starter templates)
// ---------------------------------------------------------------------------

describe('blank prices and free items print nothing', () => {
  const blankLayer = (slot: SlotBinding) =>
    ({
      id: 'l',
      type: 'text',
      slot_binding: slot,
      text_override: null,
      props: { ...defaultTextProps(), text: '' },
    }) as unknown as TagLayer;

  it('a sell price slot with no price is an empty string, no RM and no label', () => {
    expect(layerText(blankLayer('sell_price'), lineData({ sell_price: null, show_promo_price: false }), 'print')).toBe('');
    expect(layerText(blankLayer('list_price'), lineData({ list_price: null }), 'print')).toBe('');
  });

  it('a set price prints the bare figure only', () => {
    expect(layerText(blankLayer('sell_price'), lineData({ sell_price: 3090, show_promo_price: true }), 'print')).toBe('3,090');
  });

  it('free items with nothing print nothing', () => {
    expect(layerText(blankLayer('included_accessories'), lineData({ included_accessories: '' }), 'print')).toBe('');
  });
});
