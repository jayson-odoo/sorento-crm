/**
 * AC-17 (PRICETAG-ALA-CARTE): an empty Package on a product line is the salesperson's ala carte
 * choice, so "No package chosen" is dropped. "No package defined" (guarded host with no combos)
 * and "Missing: ..." (a chosen combo with parts removed) are kept.
 *
 * UAC: documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md
 */
import { describe, expect, it } from 'vitest';

import { emptyDraftLine, packageWarningFor, partsFromCombo, type DraftLine } from './price-tag-draft-lines';

const comboA = {
  combo_id: 'c1',
  name: 'Basin + tap',
  parts: [
    { product_id: 'fx', code: 'ZZTWT0001', name: 'Tap', choice_group: null },
    { product_id: 'fy', code: 'ZZTMR0002', name: 'Mirror', choice_group: null },
  ],
} as never;

const comboB = {
  combo_id: 'c2',
  name: 'Basin only',
  parts: [{ product_id: 'fz', code: 'ZZTBS0003', name: 'Basin', choice_group: null }],
} as never;

const productLine = (over: Partial<DraftLine>): DraftLine =>
  ({
    ...emptyDraftLine(),
    line_type: 'product',
    product_id: 'host',
    combos_loaded: true,
    ...over,
  }) as DraftLine;

describe('packageWarningFor: ala carte (AC-17)', () => {
  it.each([
    ['one combo', [comboA]],
    ['two combos', [comboA, comboB]],
  ])('guarded host with %s and no package chosen is ala carte: no warning', (_label, combos) => {
    const line = productLine({ host_guarded: true, combos, combo_id: null, parts: [] });
    expect(packageWarningFor(line)).toBeNull();
  });

  it('guarded host with zero combos still warns "No package defined"', () => {
    const line = productLine({ host_guarded: true, combos: [], combo_id: null, parts: [] });
    expect(packageWarningFor(line)).toBe('No package defined');
  });

  it('a chosen combo missing a fixed part still names it', () => {
    const parts = partsFromCombo(comboA).filter((p) => p.product_id !== 'fy');
    const line = productLine({ host_guarded: true, combos: [comboA, comboB], combo_id: 'c1', parts });
    expect(packageWarningFor(line)).toBe('Missing: ZZTMR0002');
  });

  it('non-guarded host with combos and no package chosen: no warning', () => {
    const line = productLine({ host_guarded: false, combos: [comboA], combo_id: null, parts: [] });
    expect(packageWarningFor(line)).toBeNull();
  });
});
