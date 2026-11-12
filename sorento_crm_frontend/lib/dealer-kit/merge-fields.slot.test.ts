/**
 * O1: per-position merge fields. `{{slot.fixed.1.code}}` reads the combo's first fixed part from
 * any text layer, through the same position code a position-bound layer uses.
 */
import { describe, expect, it } from 'vitest';

import {
  hasSubjectAwareToken,
  mergeFieldCatalog,
  renderMergeFields,
  slotTokenPath,
} from './merge-fields';
import { layerText } from './product-block';
import type { LineTagData, TagBindingData, TagLayer } from './tag-template-types';

const part = (code: string, extra: Record<string, unknown> = {}) => ({
  product_id: `id-${code}`,
  code,
  name: `${code} name`,
  dimensions: '',
  list_price: 849,
  sell_price: null,
  images: [],
  price_tag_description: `${code} desc`,
  ...extra,
});

const SLOTS = {
  main: part('MAIN1'),
  fixed: [part('FIX1'), part('FIX2')],
  groups: [{ role: 'Tap colour', size: 2, picks: [part('PICKA'), part('PICKB')] }],
  upgrades: [part('UP1')],
};

function line(slots: unknown): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 't', line_id: 'l', tag_label: '1', open_groups: [], parts: [], code: 'HOST', name: 'Host',
      dimensions: '', spec_lines: '', specs: [], set_members: '', images: [], list_price: 1, sell_price: null,
      show_promo_price: false, included_accessories: '', quantity: 1, barcode: null, slots,
    } as unknown as LineTagData,
  };
}

const render = (text: string, data: TagBindingData | null) => renderMergeFields(text, data, 'print');

describe('slot.* merge fields', () => {
  it('reads each position by its 1-based number', () => {
    const data = line(SLOTS);
    expect(render('{{slot.fixed.1.code}}/{{slot.fixed.2.code}}', data)).toBe('FIX1/FIX2');
    expect(render('{{slot.pick.1.2.code}}', data)).toBe('PICKB');
    expect(render('{{slot.upgrade.1.name}}', data)).toBe('UP1 name');
    expect(render('{{slot.main.code}}', data)).toBe('MAIN1');
    expect(render('{{slot.fixed.1.list_price}}', data)).toBe('849');
    expect(render('{{slot.fixed.2.price_tag_description}}', data)).toBe('FIX2 desc');
  });

  it('is empty for an absent position, absent slots and a line without a combo', () => {
    expect(render('[{{slot.fixed.3.code}}]', line(SLOTS))).toBe('[]');
    expect(render('[{{slot.pick.2.1.code}}]', line(SLOTS))).toBe('[]');
    expect(render('[{{slot.fixed.1.code}}]', line(undefined))).toBe('[]');
    expect(render('[{{slot.fixed.1.code}}]', line(null))).toBe('[]');
    expect(render('[{{slot.fixed.0.code}}]', line(SLOTS))).toBe('[]');
    expect(render('[{{slot.fixed.1.bogus}}]', line(SLOTS))).toBe('[]');
  });

  it('agrees with a position-bound layer', () => {
    const data = line(SLOTS);
    const bound = {
      slot_binding: 'code',
      text_override: null,
      props: { kind: 'text', text: '', subjectSlot: { kind: 'fixed', index: 1 } },
    } as unknown as TagLayer;
    expect(layerText(bound, data)).toBe(render('{{slot.fixed.2.code}}', data));
  });

  it('does not make the Product select appear on its own', () => {
    expect(hasSubjectAwareToken('{{slot.fixed.1.code}}')).toBe(false);
  });

  it('builds the 1-based token for a position', () => {
    expect(slotTokenPath({ kind: 'fixed', index: 1 }, 'code')).toBe('slot.fixed.2.code');
    expect(slotTokenPath({ kind: 'pick', group: 0, index: 1 }, 'name')).toBe('slot.pick.1.2.name');
    expect(slotTokenPath({ kind: 'main' }, 'code')).toBe('slot.main.code');
  });

  it('lists the previewed combo positions in the catalogue under Combo positions', () => {
    const fields = mergeFieldCatalog([], undefined, SLOTS as never).filter((f) => f.group === 'Combo positions');
    const pick = fields.find((f) => f.path === 'slot.pick.1.2.code');
    expect(pick?.label).toBe('Tap colour, pick 2 code: PICKB');
    expect(fields.some((f) => f.path === 'slot.fixed.1.name')).toBe(true);
    const generic = mergeFieldCatalog([], undefined, undefined).filter((f) => f.group === 'Combo positions');
    expect(generic.some((f) => f.path === 'slot.fixed.4.code')).toBe(true);
    expect(generic.some((f) => f.path === 'slot.fixed.5.code')).toBe(false);
    expect(mergeFieldCatalog([], ['Product'], SLOTS as never).some((f) => f.group === 'Combo positions')).toBe(false);
  });
});

/**
 * PRICETAG-PICK-SELLPRICE: `{{slot.pick.G.N.sell_price}}` is the combo's own "Sell price if
 * picked" for that choice (`combo.choices[].options[].sell_price`), never the part's promo offer.
 */
describe('slot.pick.G.N.sell_price', () => {
  const COMBO = {
    id: 'c', name: 'Sink combo', description: null, free_items: null, upgrades: [],
    choices: [
      {
        role: 'Tap colour',
        options: [
          { product_id: 'id-PICKA', code: 'PICKA', description: '', list_price: 270, sell_price: 899, picked: false },
          { product_id: 'id-PICKB', code: 'PICKB', description: '', list_price: 270, sell_price: 1099, picked: false },
          { product_id: 'id-PICKC', code: 'PICKC', description: '', list_price: 270, sell_price: null, picked: false },
        ],
      },
    ],
  };
  const withCombo = (slots: unknown, combo: unknown = COMBO): TagBindingData => {
    const data = line(slots);
    (data as { line: { combo?: unknown } }).line.combo = combo;
    return data;
  };
  const PREVIEW = {
    ...SLOTS,
    // The pick's own promo offer must never leak into this field.
    groups: [{ role: 'Tap colour', size: 3, picks: [part('PICKA', { sell_price: 5 }), part('PICKB'), part('PICKC')] }],
  };

  it('prints each pick its combo sell price, grouped like other tag prices', () => {
    const data = withCombo(PREVIEW);
    expect(render('{{slot.pick.1.1.sell_price}}|{{slot.pick.1.2.sell_price}}', data)).toBe('899|1,099');
  });

  it('matches the pick by product, not by its index among the options', () => {
    // A real line places only the chosen option, so pick 1 is the combo's second option.
    const data = withCombo({ ...SLOTS, groups: [{ role: 'Tap colour', size: 3, picks: [part('PICKB')] }] });
    expect(render('{{slot.pick.1.1.sell_price}}', data)).toBe('1,099');
  });

  it('is empty, never RM 0, for a blank price, a missing pick, no combo, or a non-pick slot', () => {
    expect(render('[{{slot.pick.1.3.sell_price}}]', withCombo(PREVIEW))).toBe('[]');
    expect(render('[{{slot.pick.1.4.sell_price}}]', withCombo(PREVIEW))).toBe('[]');
    expect(render('[{{slot.pick.1.1.sell_price}}]', withCombo(PREVIEW, null))).toBe('[]');
    expect(render('[{{slot.pick.1.1.sell_price}}]', line(PREVIEW))).toBe('[]');
    expect(render('[{{slot.fixed.1.sell_price}}]', withCombo(PREVIEW))).toBe('[]');
  });

  it('is offered in Insert field for picks only, labelled as the sell price if picked', () => {
    const generic = mergeFieldCatalog([], undefined, undefined).filter((f) => f.group === 'Combo positions');
    const field = generic.find((f) => f.path === 'slot.pick.1.2.sell_price');
    expect(field?.label).toBe('Choice group 1, pick 2 sell price (if picked)');
    expect(field?.token).toBe('{{slot.pick.1.2.sell_price}}');
    expect(generic.some((f) => f.path === 'slot.fixed.1.sell_price')).toBe(false);
    expect(generic.some((f) => f.path === 'slot.upgrade.1.sell_price')).toBe(false);
    const named = mergeFieldCatalog([], undefined, PREVIEW as never).find((f) => f.path === 'slot.pick.1.2.sell_price');
    expect(named?.label).toBe('Tap colour, pick 2 sell price (if picked)');
  });
});
