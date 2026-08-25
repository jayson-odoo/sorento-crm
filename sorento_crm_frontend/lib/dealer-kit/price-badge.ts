/**
 * The price badge composition, decided ONCE for both renderers.
 *
 * A price tag shows a price in exactly two shapes: a plain list price
 * (`RM 1,599`) and a promotional block (a struck `LP: RM 1,599` above a filled
 * box reading `SP RM 599 NETT`). The editor draws those with Konva and the
 * print page draws them with DOM elements, and if each decided for itself what
 * a badge is made of, the proof a salesperson approves on screen and the PDF
 * that goes to the printer would eventually disagree about a number a customer
 * reads in a showroom.
 *
 * So the COMPOSITION lives here as data - which lines exist, what each says -
 * and the two renderers only decide how to paint it. Colours, corner radius and
 * size stay editable per layer (D26); the parts do not.
 *
 * No price is ever stored in a saved document (ADR 0008). The figures handed in
 * here are resolved at render time by the pricing engine.
 */

import type { PriceBadgeLayerProps } from './tag-template-types';

/** What a tag prints when there is no price to print. */
export const NO_PRICE_TEXT = 'Price TBC';

/**
 * `RM 1,599`. Whole ringgit: a price tag in a showroom never shows cents, and
 * the flyer this feature reproduces does not either.
 */
export function formatTagPrice(amount: number): string {
  return `RM ${amount.toLocaleString('en-MY', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

export interface PriceBadgeInput {
  /** The product's list price, or null when the master data has none. */
  listPrice: number | null;
  /** The promotional price for this viewer, or null when no offer applies. */
  offerPrice: number | null;
}

export interface PriceBadgeParts {
  /** The struck-through list price above the box. Null when nothing is struck. */
  struckText: string | null;
  /** Whether the filled rounded box is drawn behind the figure. */
  boxed: boolean;
  /** The small `SP` in front of the figure. Null outside the promo variant. */
  spLabel: string | null;
  /** The main figure, already formatted. Empty when there is no price at all. */
  amountText: string;
  /** The small `NETT` after the figure. Null when the layer switches it off. */
  nettLabel: string | null;
  /**
   * The whole badge on one line, which is what a test asserts on and what a
   * screen reader gets. `Price TBC` when nothing could be resolved.
   */
  plainText: string;
}

/**
 * Decide what a price badge is made of.
 *
 * `list_only` prints the list price and nothing else - that is the tag for a
 * product that is not on offer. `promo` prints the offer, and strikes the list
 * price above it so the reader can see what they are saving; with no offer
 * resolved it degrades to the list price rather than printing an empty box,
 * because a promotion ending mid-design must not blank a tag.
 */
export function priceBadgeParts(
  props: Pick<PriceBadgeLayerProps, 'variant' | 'showNett'>,
  input: PriceBadgeInput,
): PriceBadgeParts {
  const { listPrice, offerPrice } = input;
  const promo = props.variant === 'promo' && offerPrice != null;

  if (promo) {
    const nettLabel = props.showNett ? 'NETT' : null;
    const amountText = formatTagPrice(offerPrice as number);
    return {
      struckText: listPrice != null ? `LP: ${formatTagPrice(listPrice)}` : null,
      boxed: true,
      spLabel: 'SP',
      amountText,
      nettLabel,
      plainText: ['SP', amountText, nettLabel].filter(Boolean).join(' '),
    };
  }

  if (listPrice == null) {
    return {
      struckText: null,
      boxed: false,
      spLabel: null,
      amountText: '',
      nettLabel: null,
      plainText: NO_PRICE_TEXT,
    };
  }

  const amountText = formatTagPrice(listPrice);
  return {
    struckText: null,
    boxed: false,
    spLabel: null,
    amountText,
    nettLabel: null,
    plainText: amountText,
  };
}
