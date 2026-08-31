/**
 * The price badge composition (AC-L.1).
 *
 * These assertions are what stops the editor and the print page drifting: both
 * call `priceBadgeParts`, so a change that would make the proof and the PDF
 * disagree about a price fails here first.
 */

import { describe, expect, it } from 'vitest';

import { NO_PRICE_TEXT, formatTagPrice, priceBadgeParts } from './price-badge';

const LIST_ONLY = { variant: 'list_only' as const, showNett: true };
const PROMO = { variant: 'promo' as const, showNett: true };

describe('formatTagPrice', () => {
  it('prints whole ringgit with a thousands separator', () => {
    expect(formatTagPrice(1599)).toBe('RM 1,599');
  });

  it('rounds away the cents a showroom tag never shows', () => {
    expect(formatTagPrice(1599.49)).toBe('RM 1,599');
  });
});

describe('priceBadgeParts - list_only', () => {
  it('is the list price and nothing else', () => {
    const parts = priceBadgeParts(LIST_ONLY, { listPrice: 1599, offerPrice: null });

    expect(parts.plainText).toBe('RM 1,599');
    expect(parts.amountText).toBe('RM 1,599');
    expect(parts.struckText).toBeNull();
    expect(parts.spLabel).toBeNull();
    expect(parts.nettLabel).toBeNull();
    expect(parts.boxed).toBe(false);
  });

  it('ignores an offer it was not asked to show', () => {
    const parts = priceBadgeParts(LIST_ONLY, { listPrice: 1599, offerPrice: 599 });

    expect(parts.plainText).toBe('RM 1,599');
    expect(parts.boxed).toBe(false);
  });

  it('says the price is unknown rather than printing nothing', () => {
    const parts = priceBadgeParts(LIST_ONLY, { listPrice: null, offerPrice: null });

    expect(parts.plainText).toBe(NO_PRICE_TEXT);
    expect(parts.amountText).toBe('');
  });
});

describe('priceBadgeParts - promo', () => {
  it('strikes the list price above SP RM 599 NETT', () => {
    const parts = priceBadgeParts(PROMO, { listPrice: 1599, offerPrice: 599 });

    expect(parts.struckText).toBe('LP: RM 1,599');
    expect(parts.spLabel).toBe('SP');
    expect(parts.amountText).toBe('RM 599');
    expect(parts.nettLabel).toBe('NETT');
    expect(parts.plainText).toBe('SP RM 599 NETT');
    expect(parts.boxed).toBe(true);
  });

  it('drops NETT when the layer switches it off', () => {
    const parts = priceBadgeParts(
      { variant: 'promo', showNett: false },
      { listPrice: 1599, offerPrice: 599 },
    );

    expect(parts.nettLabel).toBeNull();
    expect(parts.plainText).toBe('SP RM 599');
  });

  it('falls back to the list price when the promotion has ended', () => {
    // A tag whose offer disappears mid-design must print the list price, not an
    // empty red box.
    const parts = priceBadgeParts(PROMO, { listPrice: 1599, offerPrice: null });

    expect(parts.plainText).toBe('RM 1,599');
    expect(parts.boxed).toBe(false);
    expect(parts.struckText).toBeNull();
  });

  it('still shows the offer when the product has no list price to strike', () => {
    const parts = priceBadgeParts(PROMO, { listPrice: null, offerPrice: 599 });

    expect(parts.struckText).toBeNull();
    expect(parts.plainText).toBe('SP RM 599 NETT');
  });
});
