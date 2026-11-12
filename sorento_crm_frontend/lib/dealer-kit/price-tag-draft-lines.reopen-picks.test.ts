/**
 * PRICETAG-UPGRADE-VARIANTS crew re-pass (2): a reopened line stores its picks only, so a single
 * Upgrade pick came back with no candidates and rendered as a static part instead of its picker. Once
 * the combos lookup answers, the Upgrade row gets its options back, keeping the pick. A lone group
 * pick keeps today's rule (a resolved part, `price-tag-draft-lines.reopen.test.ts`).
 */
import { describe, expect, it } from 'vitest';

import { restoreGroupCandidates, type DraftPart } from './price-tag-draft-lines';

const combo = {
  combo_id: 'c1',
  name: 'UPGRADE TEST',
  parts: [
    { product_id: 'fix', code: 'SRTKT1862SS', name: 'Kitchen tap', choice_group: null, is_upgrade: false },
    { product_id: 'g1', code: 'TAP-A', name: 'Tap A', choice_group: 'Tap', is_upgrade: false },
    { product_id: 'g2', code: 'TAP-B', name: 'Tap B', choice_group: 'Tap', is_upgrade: false },
    { product_id: 'up', code: 'SRTKT71SS', name: 'Pull-out mixer', choice_group: null, is_upgrade: true, topup_amount: 150 },
  ],
} as unknown as Parameters<typeof restoreGroupCandidates>[1];

const row = (over: Partial<DraftPart>): DraftPart => ({
  key: over.key ?? 'k',
  product_id: null,
  code: '',
  name: '',
  role: null,
  candidates: [],
  ...over,
});

describe('restoreGroupCandidates: reopened single picks get their picker back', () => {
  it('the picked Upgrade row gets the upgrade options and keeps its pick', () => {
    const [out] = restoreGroupCandidates(
      [row({ role: 'Upgrade', product_id: 'up', code: 'SRTKT71SS' })],
      combo,
    );
    expect(out.product_id).toBe('up');
    expect(out.candidates.map((c) => c.product_id)).toEqual(['up']);
    expect((out.candidates[0] as { topup_amount?: number | null }).topup_amount).toBe(150);
  });

  it('a lone pick of a choice group stays a resolved part (unchanged rule)', () => {
    const lone = [row({ role: 'Tap', product_id: 'g2', code: 'TAP-B' })];
    expect(restoreGroupCandidates(lone, combo)[0].candidates).toEqual([]);
  });

  it('a multi-pick row still gets its group options (unchanged)', () => {
    const [out] = restoreGroupCandidates(
      [row({ role: 'Tap', product_id: 'g1', product_ids: ['g1', 'g2'] })],
      combo,
    );
    expect(out.candidates.map((c) => c.product_id)).toEqual(['g1', 'g2']);
  });

  it('a fixed part and a row that already has candidates are left alone', () => {
    const fixed = row({ product_id: 'fix', code: 'SRTKT1862SS' });
    const open = row({ role: 'Tap', candidates: [{ product_id: 'g1', code: 'TAP-A', name: 'Tap A' }] });
    const out = restoreGroupCandidates([fixed, open], combo);
    expect(out[0]).toBe(fixed);
    expect(out[1]).toBe(open);
  });

  it('no combo answer leaves the rows alone', () => {
    const parts = [row({ role: 'Upgrade', product_id: 'up' })];
    expect(restoreGroupCandidates(parts, undefined)).toBe(parts);
  });
});
