/**
 * Barcode symbology (AC-S7-3, AC-S7-6). The drawn label itself (layout, scan
 * check) is pinned in `barcode-svg.test.ts`.
 *
 * Real checksum-valid EAN-13 values, not just "13 digits" - a barcode layer
 * that rendered EAN-13 bars for a mistyped 13-digit number would encode the
 * wrong product on a printed tag.
 */

import { describe, expect, it } from 'vitest';

import { barcodeSymbologyFor, isValidEAN13 } from './barcode';

// Real, checksum-valid EAN-13 values.
const VALID_EAN13 = '4006381333931';
const VALID_EAN13_2 = '1234567890128';
// Same digits as VALID_EAN13 with the check digit flipped.
const INVALID_CHECKSUM_13 = '4006381333932';

describe('isValidEAN13', () => {
  it('accepts a checksum-valid 13-digit value', () => {
    expect(isValidEAN13(VALID_EAN13)).toBe(true);
    expect(isValidEAN13(VALID_EAN13_2)).toBe(true);
  });

  it('rejects 13 digits with the wrong check digit', () => {
    expect(isValidEAN13(INVALID_CHECKSUM_13)).toBe(false);
  });

  it('rejects a value that is not 13 digits', () => {
    expect(isValidEAN13('123456789012')).toBe(false); // 12
    expect(isValidEAN13('12345678901234')).toBe(false); // 14
  });

  it('rejects a non-numeric value of the right length', () => {
    expect(isValidEAN13('400638133393A')).toBe(false);
  });

  it('tolerates surrounding whitespace', () => {
    expect(isValidEAN13(`  ${VALID_EAN13}  `)).toBe(true);
  });
});

describe('barcodeSymbologyFor', () => {
  it('is EAN13 for a checksum-valid 13-digit value', () => {
    expect(barcodeSymbologyFor(VALID_EAN13)).toBe('EAN13');
  });

  it('is CODE128 for a 13-digit value with a bad checksum', () => {
    expect(barcodeSymbologyFor(INVALID_CHECKSUM_13)).toBe('CODE128');
  });

  it('is CODE128 for any other non-empty value', () => {
    expect(barcodeSymbologyFor('SKU-1234')).toBe('CODE128');
    expect(barcodeSymbologyFor('12345')).toBe('CODE128');
  });

  it('is null for an empty, whitespace-only, or missing value', () => {
    expect(barcodeSymbologyFor('')).toBeNull();
    expect(barcodeSymbologyFor('   ')).toBeNull();
    expect(barcodeSymbologyFor(null)).toBeNull();
    expect(barcodeSymbologyFor(undefined)).toBeNull();
  });
});
