/** PRICETAG-COMBO AC-3.5: an upgrade reaches the line as one open row, never a fixed part. */
import { describe, expect, it } from 'vitest';

import { emptyDraftLine, packageWarningFor, partsFromCombo } from './price-tag-draft-lines';

const COMBO = {
  combo_id: 'c1',
  name: '3 in 1',
  parts: [
    { product_id: 'p-mirror', code: 'ZZMIR', name: 'Mirror', choice_group: null },
    { product_id: 'p-white', code: 'ZZW', name: 'White', choice_group: 'Basin' },
    { product_id: 'p-black', code: 'ZZB', name: 'Black', choice_group: 'Basin' },
    { product_id: 'p-stone', code: 'ZZU', name: 'Stone', choice_group: null, is_upgrade: true },
  ],
};

describe('partsFromCombo with an upgrade', () => {
  it('puts a single upgrade in one open Upgrade row, not resolved', () => {
    const parts = partsFromCombo(COMBO);
    const upgrade = parts.filter((part) => part.role === 'Upgrade');
    expect(upgrade).toHaveLength(1);
    expect(upgrade[0].product_id).toBeNull();
    expect(upgrade[0].candidates.map((c) => c.product_id)).toEqual(['p-stone']);
    // The upgrade is not also a fixed row.
    expect(parts.filter((part) => part.product_id === 'p-stone')).toHaveLength(0);
    expect(parts.find((part) => part.product_id === 'p-mirror')).toBeDefined();
  });

  it('groups several upgrades in the same one row', () => {
    const second = { product_id: 'p-glass', code: 'ZZG', name: 'Glass', choice_group: null, is_upgrade: true };
    const parts = partsFromCombo({ ...COMBO, parts: [...COMBO.parts, second] });
    const row = parts.find((part) => part.role === 'Upgrade');
    expect(row?.candidates).toHaveLength(2);
    expect(parts.filter((part) => part.role === 'Upgrade')).toHaveLength(1);
  });

  it('draws no Upgrade row when the combo has none', () => {
    const parts = partsFromCombo({ ...COMBO, parts: COMBO.parts.slice(0, 3) });
    expect(parts.some((part) => part.role === 'Upgrade')).toBe(false);
  });

  it('never names an unanswered upgrade in the Missing warning', () => {
    const parts = partsFromCombo(COMBO).filter((part) => part.role !== 'Upgrade');
    const line = {
      ...emptyDraftLine(),
      product_id: 'host',
      combos: [COMBO],
      combos_loaded: true,
      host_guarded: true,
      combo_id: 'c1',
      parts,
    };
    expect(packageWarningFor(line)).toBeNull();
  });
});
