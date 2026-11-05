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
