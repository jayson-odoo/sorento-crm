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
