/**
 * Formatting shared between `ProductSuppliedWithSection` and `ProductShipsWithSection`
 * (PLAN-scm-supplied-with-companions.md).
 */

/**
 * `1`, not `1.0000` - the backend's `Decimal` field is a string on the wire (the same
 * "qty style" convention `formatInquiryQty` uses for order inquiry quantities), and a
 * NUMERIC(15,4) column prints every trailing zero unless something trims them for the
 * reader.
 */
export function formatRatio(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  const text = String(value).trim();
  if (text === '' || !/^-?\d+(\.\d+)?$/.test(text)) return text;
  return text.includes('.') ? text.replace(/\.?0+$/, '') : text;
}
