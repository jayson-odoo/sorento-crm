import { describe, it, expect } from 'vitest';

import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
  PRICE_TAG_STATUS_PILL_CLASS,
} from './price-tag-status';

// AC-S1-5 / AC-S1-7 (PLAN-price-tag-r7-request-ux): "Proof" renamed to
// "Design" in every user-visible label; enum VALUES are untouched (D2/D9).
describe('price-tag-status (r7 D9: Proof -> Design labels)', () => {
  it('proof_ready reads "Design Ready", not "Proof Ready"', () => {
    expect(priceTagStatusLabel('proof_ready')).toBe('Design Ready');
  });

  it('every other status label is unchanged by the rename', () => {
    expect(priceTagStatusLabel('new')).toBe('New');
    expect(priceTagStatusLabel('designing')).toBe('Designing');
    expect(priceTagStatusLabel('changes_requested')).toBe('Changes Requested');
    expect(priceTagStatusLabel('approved')).toBe('Approved');
    expect(priceTagStatusLabel('ready')).toBe('Ready');
    expect(priceTagStatusLabel('rejected')).toBe('Rejected');
    expect(priceTagStatusLabel('void')).toBe('Void');
    expect(priceTagStatusLabel('draft')).toBe('Draft');
  });

  it('is case-insensitive', () => {
    expect(priceTagStatusLabel('PROOF_READY')).toBe('Design Ready');
  });

  it('the enum VALUE itself is untouched - only the label reads differently', () => {
    // The pill-colour map is still keyed by the raw enum value `proof_ready`,
    // not a renamed `design_ready` - a route, a column or a listener that
    // reads the raw status must never see the label word.
    expect(PRICE_TAG_STATUS_PILL_CLASS).toHaveProperty('proof_ready');
    expect(PRICE_TAG_STATUS_PILL_CLASS).not.toHaveProperty('design_ready');
    const pill = priceTagStatusPillClass('proof_ready');
    expect(pill).toBe(PRICE_TAG_STATUS_PILL_CLASS.proof_ready);
    expect(pill).not.toBe(priceTagStatusPillClass('something-unknown'));
  });

  it('an unknown status falls back to a title-cased word rather than throwing', () => {
    expect(priceTagStatusLabel('some_unknown_status')).toBe('Some Unknown Status');
  });
});
