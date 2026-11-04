/** PRICETAG-COMBO-RENDER fix round 1 (F2): a reopened multi-pick row gets its group's candidates back. */
import { describe, expect, it } from 'vitest';

import { lineToDraft, restoreGroupCandidates } from './price-tag-draft-lines';

const CODES = ['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'];
const id = (c: string) => `id-${c}`;
const combo = {
  combo_id: 'c1',
  name: 'Sink combo',
  parts: [
    ...CODES.map((c) => ({ product_id: id(c), code: c, name: c, choice_group: 'Kitchen tap', is_discontinued: false })),
    { product_id: id('SRTKT71SS'), code: 'SRTKT71SS', name: 'Up', choice_group: null, is_upgrade: true },
  ],
};

const saved = (picks: string[]) =>
  ({
    id: 'line-1', line_type: 'product', product_id: 'host', product_set_id: null, name: 'Host', code: 'H',
    quantity: 1, combo_id: 'c1',
    parts: picks.map((c, i) => ({ id: `p${i}`, product_id: id(c), code: c, name: c, role: 'Kitchen tap', candidates: [] })),
  }) as never;

describe('restoreGroupCandidates', () => {
  it('gives the folded row the combo group options, the picks kept in saved order', () => {
    const draft = lineToDraft(saved([CODES[2], CODES[0], CODES[1]]));
    expect(draft.parts).toHaveLength(1);
    expect(draft.parts[0].candidates).toEqual([]);
    const [row] = restoreGroupCandidates(draft.parts, combo);
    expect(row.candidates.map((c) => c.code)).toEqual(CODES);
    expect(row.product_ids).toEqual([id(CODES[2]), id(CODES[0]), id(CODES[1])]);
  });

  it('leaves a lone resolved part and a row that already has candidates alone', () => {
    const lone = lineToDraft(saved([CODES[0]])).parts;
    expect(restoreGroupCandidates(lone, combo)).toEqual(lone);
    const folded = lineToDraft(saved([CODES[0], CODES[1]])).parts;
    const once = restoreGroupCandidates(folded, combo);
    expect(restoreGroupCandidates(once, combo)).toEqual(once);
  });

  it('does nothing without a combo or for a role the combo lacks', () => {
    const folded = lineToDraft(saved([CODES[0], CODES[1]])).parts;
    expect(restoreGroupCandidates(folded, undefined)).toEqual(folded);
    expect(restoreGroupCandidates(folded, { ...combo, parts: [] })[0].candidates).toEqual([]);
  });
});
