/**
 * Barcode symbology + display rules for the tag editor's barcode layer (S7,
 * PLAN D18 / D14).
 *
 * Pure and DOM-free on purpose, so the symbology decision and the
 * human-readable text are testable without a browser, and cannot drift
 * between the Konva editor and the print page's DOM renderer - both call
 * these before touching `jsbarcode`.
 */

export type BarcodeSymbology = 'EAN13' | 'CODE128';

/**
 * EAN-13 check digit (GS1 mod-10, alternating x1/x3 from the left,
 * left-to-right on the first 12 digits). `value` must already be 13 digits.
 */
function ean13CheckDigitValid(value: string): boolean {
  const digits = value.split('').map(Number);
  const check = digits[12];
  let sum = 0;
  for (let i = 0; i < 12; i += 1) {
    sum += digits[i] * (i % 2 === 0 ? 1 : 3);
  }
  const computed = (10 - (sum % 10)) % 10;
  return computed === check;
}

/** A real, checksum-valid EAN-13 - not just "13 digits" (D18). */
export function isValidEAN13(value: string): boolean {
  const trimmed = value.trim();
  if (!/^\d{13}$/.test(trimmed)) return false;
  return ean13CheckDigitValid(trimmed);
}

/**
 * Which symbology a barcode value renders as (S7): a checksum-valid 13-digit
 * numeric is EAN-13, any other non-empty value is Code128, and an empty value
 * has no symbology at all - the caller draws its placeholder instead.
 */
export function barcodeSymbologyFor(value: string | null | undefined): BarcodeSymbology | null {
  const trimmed = (value ?? '').trim();
  if (!trimmed) return null;
  return isValidEAN13(trimmed) ? 'EAN13' : 'CODE128';
}

/**
 * The human-readable text under the bars. EAN-13 guard-splits into
 * `digit space group-of-6 space group-of-6`, matching the guard bars printed
 * either side of it; Code128 has no guard bars, so it prints plain.
 */
export function humanReadableBarcode(value: string, symbology: BarcodeSymbology): string {
  const trimmed = value.trim();
  if (symbology === 'EAN13' && trimmed.length === 13) {
    return `${trimmed[0]} ${trimmed.slice(1, 7)} ${trimmed.slice(7, 13)}`;
  }
  return trimmed;
}

// ---------------------------------------------------------------------------
// Label plate geometry (D18, S7 review fix)
// ---------------------------------------------------------------------------

/**
 * 1mm in CSS `pt`. The print page's other layers (text, price badge) already
 * size their fonts in `pt` - `font-size: <n>mm` is a much larger typeface than
 * `<n>pt` for the same number, which is exactly the bug this constant exists
 * to prevent from coming back: the plate's font sizes are computed in
 * mm-of-plate below and MUST cross this factor before they reach a `fontSize`
 * style, never render as a bare `${n}mm`.
 */
export const MM_TO_PT = 2.8346;

/**
 * The label plate's band layout (D18), in millimetres of the PLATE itself -
 * unit-free, so it means the same thing whether the caller then multiplies by
 * a Konva canvas scale (px) or by `MM_TO_PT` (pt). This one function is what
 * keeps the Konva editor's preview and the print page's DOM/CSS in agreement:
 * before this existed each file carried its own copy of these ratios, and the
 * print page's copy multiplied its font floor as if it were already millimetres
 * when it was written against canvas pixels - a 6mm floor on a ~4mm band, which
 * forced an oversized font and squeezed the bars into a fraction of the plate.
 */
export interface BarcodePlateGeometry {
  /** Corner radius of the white backing, and the bars' left/right padding. */
  cornerRadius_mm: number;
  /** 0 when the product-code strip is not shown. */
  stripHeight_mm: number;
  humanHeight_mm: number;
  /** Top offset of the bars band (equal to `stripHeight_mm`). */
  barsY_mm: number;
  barsHeight_mm: number;
  barsX_mm: number;
  barsWidth_mm: number;
  /** 0 when the strip is not shown. */
  stripFontSize_mm: number;
  humanFontSize_mm: number;
}

const STRIP_RATIO = 0.18;
const HUMAN_BAND_RATIO = 0.16;
/** Corner radius AND the bars' left/right padding - the plate always used one
 * ratio for both, so a single constant is what "lift the constants" means here. */
const PADDING_RATIO = 0.06;
const BARS_WIDTH_RATIO = 0.88;
const FONT_RATIO = 0.6;
/**
 * Minimum font size, in mm of plate. Derived from the Konva editor's original
 * `6` (a floor in CANVAS PIXELS) at the editor's base scale,
 * `CANVAS_PX_PER_MM = 3` (`lib/dealer-kit/canvas-geometry.ts`) - `6px / 3 =
 * 2mm`. A print plate at typical sizes never hits this floor (see the 40x22mm
 * case in `barcode.test.ts`); it only guards a plate small enough that the
 * ratio-derived size would be unreadable.
 */
const MIN_FONT_MM = 2;

export function barcodePlateGeometry(
  width_mm: number,
  height_mm: number,
  showStrip: boolean,
): BarcodePlateGeometry {
  const stripHeight_mm = showStrip ? height_mm * STRIP_RATIO : 0;
  const humanHeight_mm = height_mm * HUMAN_BAND_RATIO;
  const barsY_mm = stripHeight_mm;
  const barsHeight_mm = Math.max(0, height_mm - stripHeight_mm - humanHeight_mm);
  const cornerRadius_mm = Math.min(width_mm, height_mm) * PADDING_RATIO;

  return {
    cornerRadius_mm,
    stripHeight_mm,
    humanHeight_mm,
    barsY_mm,
    barsHeight_mm,
    barsX_mm: width_mm * PADDING_RATIO,
    barsWidth_mm: width_mm * BARS_WIDTH_RATIO,
    stripFontSize_mm: stripHeight_mm > 0 ? Math.max(MIN_FONT_MM, stripHeight_mm * FONT_RATIO) : 0,
    humanFontSize_mm: Math.max(MIN_FONT_MM, humanHeight_mm * FONT_RATIO),
  };
}
