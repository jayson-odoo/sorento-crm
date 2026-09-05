/**
 * The price badge composition (AC-L.1).
 *
 * These assertions are what stops the editor and the print page drifting: both
 * call `priceBadgeParts`, so a change that would make the proof and the PDF
 * disagree about a price fails here first.
 */

import { describe, expect, it } from 'vitest';

import {
  NO_PRICE_TEXT,
  formatTagPrice,
  priceBadgeParts,
  priceBadgeTypography,
} from './price-badge';

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

describe('priceBadgeParts - the list-only box (r4b, AC-S6-1)', () => {
  it('draws the box when the layer asks for one', () => {
    const parts = priceBadgeParts(
      { ...LIST_ONLY, showBox: true },
      { listPrice: 1599, offerPrice: null },
    );

    expect(parts.boxed).toBe(true);
    // The whole layer box, drawn from the layer's own corners.
    expect(parts.polygonBox).toBe(true);
    // Only the box arrives - a list-only badge is still just the figure.
    expect(parts.plainText).toBe('RM 1,599');
    expect(parts.spLabel).toBeNull();
    expect(parts.nettLabel).toBeNull();
    expect(parts.struckText).toBeNull();
  });

  it('draws no box for a badge saved before the flag existed (AC-S6-1)', () => {
    expect(priceBadgeParts(LIST_ONLY, { listPrice: 1599, offerPrice: null }).boxed).toBe(false);
    expect(
      priceBadgeParts({ ...LIST_ONLY, showBox: false }, { listPrice: 1599, offerPrice: null })
        .boxed,
    ).toBe(false);
  });

  it('draws no box around a price it does not have', () => {
    const parts = priceBadgeParts(
      { ...LIST_ONLY, showBox: true },
      { listPrice: null, offerPrice: null },
    );

    expect(parts.boxed).toBe(false);
    expect(parts.plainText).toBe(NO_PRICE_TEXT);
  });

  it('keeps the box when a promo badge that asked for one loses its offer', () => {
    // The fallback branch is shared, and the flag is read there rather than
    // gated on the variant: a promotion ending mid-design already degrades
    // the badge to the list price, and taking the callout away at the same
    // moment would be a second, unrelated jump on the tag.
    const parts = priceBadgeParts(
      { ...PROMO, showBox: true },
      { listPrice: 1599, offerPrice: null },
    );

    expect(parts.boxed).toBe(true);
    expect(parts.plainText).toBe('RM 1,599');
  });

  it('leaves the promo variant exactly as it was (AC-S6-3)', () => {
    expect(priceBadgeParts(PROMO, { listPrice: 1599, offerPrice: 599 }).boxed).toBe(true);
    // The promotional block keeps its rounded rectangle under the struck
    // price: it is the one box whose height the print page cannot state in
    // millimetres, and nothing about promo changes here (AC-S6-3).
    expect(priceBadgeParts(PROMO, { listPrice: 1599, offerPrice: 599 }).polygonBox).toBe(false);
    expect(
      priceBadgeParts({ ...PROMO, showBox: false }, { listPrice: 1599, offerPrice: 599 }).boxed,
    ).toBe(true);
  });
});

describe('priceBadgeTypography (r4b, AC-S6-4/5)', () => {
  it('resolves an untouched badge to "whatever each renderer already did"', () => {
    // Null, not a number: the canvas sizes the figure from the box and the
    // print page uses a fixed pt, and a badge saved before these fields has
    // to keep printing exactly as it did (AC-S6-5).
    expect(priceBadgeTypography({})).toEqual({
      fontFamily: null,
      fontSize: null,
      fontWeight: null,
      italic: false,
      underline: false,
      strikethrough: false,
      align: 'center',
      lineHeight: null,
      letterSpacing: 0,
    });
  });

  it('hands back what the layer actually carries', () => {
    expect(
      priceBadgeTypography({
        fontFamily: 'Bebas Neue',
        fontSize: 22,
        fontWeight: 900,
        italic: true,
        underline: true,
        strikethrough: true,
        align: 'left',
        lineHeight: 1.4,
        letterSpacing: 0.5,
      }),
    ).toEqual({
      fontFamily: 'Bebas Neue',
      fontSize: 22,
      fontWeight: 900,
      italic: true,
      underline: true,
      strikethrough: true,
      align: 'left',
      lineHeight: 1.4,
      letterSpacing: 0.5,
    });
  });
});
