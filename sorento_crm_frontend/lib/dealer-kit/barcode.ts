/**
 * The barcode layer (S7, PLAN D18 / D14): symbology, and the whole label drawn
 * as ONE SVG (PRICETAG-BARCODE-MATCH).
 *
 * Pure and DOM-free on purpose. The Konva canvas, the request preview and the
 * printed PDF all draw the string `barcodeSvg` returns, through the browser's
 * own SVG rasteriser, so the three cannot lay the barcode out differently.
 */

import JsBarcode from 'jsbarcode';

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

// ---------------------------------------------------------------------------
// The label, as one SVG (PRICETAG-BARCODE-MATCH)
// ---------------------------------------------------------------------------

/*
 * Layout of the barcode staff already print: product code above the bars in
 * a black serif with no box behind it, standard EAN-13 guard bars running
 * down into the digit row, each digit centred in its own 7-module cell (the
 * first one in the left quiet zone), white background.
 *
 * Every length below is a multiple of the module width X (EAN) or of the
 * base font F, and F is a fraction of the box, so a box twice the size is the
 * same drawing at twice the size: there is no absolute floor that could make
 * a zoomed or resized layer look different.
 */

/** GS1 quiet zones, in modules: the left one also holds the first digit. */
const EAN_QUIET_LEFT = 11;
const EAN_QUIET_RIGHT = 7;
const EAN_MODULES = 95;
/** Module ranges of the start, centre and end guards inside the symbol. */
const EAN_GUARDS: ReadonlyArray<readonly [number, number]> = [
  [0, 2],
  [45, 49],
  [92, 94],
];
const CODE128_QUIET = 10;

/** A monospace digit is about 0.6em wide, so 10.5X fills its 7X cell with a
 * hair of white either side (11X touched the guard bars). */
const DIGIT_FONT_MODULES = 10.5;
/** The font gives way to the height in a squat box so the bars stay tall. */
const MAX_FONT_SHARE_OF_HEIGHT = 0.22;
const MONO_ADVANCE_EM = 0.6;
/** Distances in units of the font size, top to bottom. */
const PAD_EM = 0.15;
const CODE_BASELINE_EM = 0.75;
const CODE_GAP_EM = 0.5;
const DIGIT_BARS_GAP_EM = 0.8;
const GUARD_EXTENSION_EM = 0.45;
/** A longer code is compressed to this share of the width, never clipped. */
const CODE_MAX_WIDTH_SHARE = 0.94;

const CODE_FONT = "'Times New Roman', Times, serif";
const DIGIT_FONT = "'OCR-B', OCRB, Menlo, Consolas, 'DejaVu Sans Mono', monospace";

export interface BarcodeSvgInput {
  value: string | null | undefined;
  /** The product code printed above the bars. */
  code: string | null | undefined;
  showCode: boolean;
  /** The layer box; the SVG's viewBox is this box, in mm. */
  widthMm: number;
  heightMm: number;
}

/** The bars as a string of modules, `1` = bar, or null if it cannot encode. */
function encodeModules(value: string, symbology: BarcodeSymbology): string | null {
  const target: { encodings?: Array<{ data: string }> } = {};
  try {
    // A plain object target is jsbarcode's DOM-free "object" renderer.
    JsBarcode(target, value, { format: symbology, flat: true });
  } catch {
    return null;
  }
  const modules = (target.encodings ?? []).map((e) => e.data).join('');
  return /^[01]+$/.test(modules) ? modules : null;
}

/** Rough advance widths of a Times-like face, in em, to tell when a code is
 * too long for the box. Only decides whether to compress it - never where it
 * sits. */
function serifWidthEm(text: string): number {
  let em = 0;
  for (const ch of text) {
    if (/[0-9]/.test(ch)) em += 0.5;
    else if (/[A-Z]/.test(ch)) em += 0.68;
    else if (/[a-z]/.test(ch)) em += 0.46;
    else if (ch === ' ') em += 0.25;
    else if (ch === '-' || ch === '.') em += 0.33;
    else em += 0.55;
  }
  return em;
}

function n(value: number): string {
  return String(Number(value.toFixed(3)));
}

function xml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function textEl(
  content: string,
  x: number,
  y: number,
  size: number,
  family: string,
  extra = '',
): string {
  return (
    `<text x="${n(x)}" y="${n(y)}" font-size="${n(size)}" font-family="${family}"` +
    ` text-anchor="middle" fill="#000000"${extra}>${xml(content)}</text>`
  );
}

/**
 * The whole barcode label for a layer box, as an SVG string, or null when
 * there is nothing to draw (empty value) or the value cannot be encoded.
 * EAN-13 for a checksum-valid 13-digit value, Code128 for anything else.
 */
export function barcodeSvg(input: BarcodeSvgInput): string | null {
  const value = (input.value ?? '').trim();
  const symbology = barcodeSymbologyFor(value);
  if (!symbology) return null;
  const modules = encodeModules(value, symbology);
  if (!modules) return null;

  const W = input.widthMm;
  const H = input.heightMm;
  const isEan = symbology === 'EAN13' && modules.length === EAN_MODULES;
  const quietLeft = isEan ? EAN_QUIET_LEFT : CODE128_QUIET;
  const quietRight = isEan ? EAN_QUIET_RIGHT : CODE128_QUIET;
  const X = W / (quietLeft + modules.length + quietRight);
  // The base font is what an EAN-13 in this box would use, for Code128 too,
  // so the code above the bars reads the same size either way.
  const eanModuleWidth = W / (EAN_QUIET_LEFT + EAN_MODULES + EAN_QUIET_RIGHT);
  const F = Math.min(DIGIT_FONT_MODULES * eanModuleWidth, MAX_FONT_SHARE_OF_HEIGHT * H);
  const pad = PAD_EM * F;
  const code = (input.code ?? '').trim();
  const showCode = input.showCode && code.length > 0;

  const parts: string[] = [`<rect x="0" y="0" width="${n(W)}" height="${n(H)}" fill="#ffffff"/>`];

  let barsTop = pad;
  if (showCode) {
    const available = W * CODE_MAX_WIDTH_SHARE;
    const fit =
      serifWidthEm(code) * F > available
        ? ` textLength="${n(available)}" lengthAdjust="spacingAndGlyphs"`
        : '';
    parts.push(textEl(code, W / 2, pad + CODE_BASELINE_EM * F, F, CODE_FONT, fit));
    barsTop = pad + (CODE_BASELINE_EM + CODE_GAP_EM) * F;
  }

  const baseline = H - pad;
  // Code128 prints its value as one line, shrunk to the width if it must be.
  const valueFont = isEan
    ? F
    : Math.min(F, (W - 2 * quietLeft * X) / (MONO_ADVANCE_EM * Math.max(1, value.length)));
  const barsBottom = baseline - DIGIT_BARS_GAP_EM * valueFont;
  const guardBottom = barsBottom + GUARD_EXTENSION_EM * F;

  for (let i = 0; i < modules.length; ) {
    if (modules[i] !== '1') {
      i += 1;
      continue;
    }
    let end = i;
    while (end < modules.length && modules[end] === '1') end += 1;
    const start = i;
    const guard = isEan && EAN_GUARDS.some(([a, b]) => start >= a && start <= b);
    const bottom = guard ? guardBottom : barsBottom;
    parts.push(
      `<rect x="${n((quietLeft + start) * X)}" y="${n(barsTop)}" width="${n((end - start) * X)}"` +
        ` height="${n(bottom - barsTop)}" fill="#000000"/>`,
    );
    i = end;
  }

  if (isEan) {
    // First digit in the left quiet zone, then 6 + 6 between the guards.
    parts.push(textEl(value[0], (EAN_QUIET_LEFT - 5) * X, baseline, F, DIGIT_FONT));
    for (let d = 0; d < 12; d += 1) {
      const cell = d < 6 ? 3 + d * 7 : 50 + (d - 6) * 7;
      parts.push(
        textEl(value[d + 1], (EAN_QUIET_LEFT + cell + 3.5) * X, baseline, F, DIGIT_FONT),
      );
    }
  } else {
    parts.push(textEl(value, W / 2, baseline, valueFont, DIGIT_FONT));
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${n(W)}mm" height="${n(H)}mm"` +
    ` viewBox="0 0 ${n(W)} ${n(H)}">${parts.join('')}</svg>`
  );
}

/** The SVG as a data: URL, for an `<img>` or a Konva image to load. */
export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
