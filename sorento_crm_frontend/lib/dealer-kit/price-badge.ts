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

/** What a badge's figure is set in, once every absent field is resolved. */
export interface PriceBadgeTypography {
  /** Null = the renderer's own default face. */
  fontFamily: string | null;
  /** Points. Null = the size the renderer already derives from the box. */
  fontSize: number | null;
  /** Null = the weight the renderer already uses (the figure is bold). */
  fontWeight: number | null;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  align: 'left' | 'center' | 'right';
  /** Null = the renderer's own default leading. */
  lineHeight: number | null;
  letterSpacing: number;
}

/**
 * Resolve a badge's typography, ONE place for both renderers (r4b, AC-S6-4).
 *
 * Three fields resolve to `null` rather than to a number, and that is
 * deliberate: the canvas sizes the figure from the layer box while the print
 * page uses a fixed point size, so there is no single number that means "what
 * this badge already looked like". Null hands that decision back to whichever
 * renderer is asking, which is what keeps a badge saved before these fields
 * printing exactly as it did (AC-S6-5).
 */
export function priceBadgeTypography(
  props: Partial<
    Pick<
      PriceBadgeLayerProps,
      | 'fontFamily'
      | 'fontSize'
      | 'fontWeight'
      | 'italic'
      | 'underline'
      | 'strikethrough'
      | 'align'
      | 'lineHeight'
      | 'letterSpacing'
    >
  >,
): PriceBadgeTypography {
  return {
    fontFamily: props.fontFamily ?? null,
    fontSize: props.fontSize ?? null,
    fontWeight: props.fontWeight ?? null,
    italic: props.italic ?? false,
    underline: props.underline ?? false,
    strikethrough: props.strikethrough ?? false,
    align: props.align ?? 'center',
    lineHeight: props.lineHeight ?? null,
    letterSpacing: props.letterSpacing ?? 0,
  };
}

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
  /**
   * The box is the WHOLE layer box, drawn from the layer's own `points`
   * (r4b, AC-S6-2) - the flyer's slanted white callout, which is the badge
   * itself rather than a shape behind it.
   *
   * False for the promotional block, whose box is only the part of the layer
   * left under the struck price. That one keeps the rounded rectangle it has
   * always had, in both renderers, because a promo badge is unchanged by this
   * (AC-S6-3) - and it is also the only box whose height neither renderer can
   * state in millimetres, the print page laying it out with flex.
   */
  polygonBox: boolean;
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
 * product that is not on offer, in a box only if the layer asks for one. `promo` prints the offer, and strikes the list
 * price above it so the reader can see what they are saving; with no offer
 * resolved it degrades to the list price rather than printing an empty box,
 * because a promotion ending mid-design must not blank a tag.
 */
export function priceBadgeParts(
  props: Pick<PriceBadgeLayerProps, 'variant' | 'showNett'> &
    Partial<Pick<PriceBadgeLayerProps, 'showBox'>>,
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
      polygonBox: false,
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
      polygonBox: false,
      spLabel: null,
      amountText: '',
      nettLabel: null,
      plainText: NO_PRICE_TEXT,
    };
  }

  const amountText = formatTagPrice(listPrice);
  return {
    struckText: null,
    // The white callout on the flyer IS the badge, not a shape behind it
    // (r4b, AC-S6-1). Opt-in, so a list-only badge saved before the flag -
    // and there are eight seeded templates full of them - prints unchanged.
    boxed: props.showBox === true,
    polygonBox: props.showBox === true,
    spLabel: null,
    amountText,
    nettLabel: null,
    plainText: amountText,
  };
}
