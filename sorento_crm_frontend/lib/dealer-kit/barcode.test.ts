/**
 * Barcode symbology + human-readable text (AC-S7-3, AC-S7-6).
 *
 * Real checksum-valid EAN-13 values, not just "13 digits" - a barcode layer
 * that rendered EAN-13 bars for a mistyped 13-digit number would encode the
 * wrong product on a printed tag.
 */

import { describe, expect, it } from 'vitest';

import {
  barcodePlateGeometry,
  barcodeSymbologyFor,
  humanReadableBarcode,
  isValidEAN13,
  MM_TO_PT,
} from './barcode';

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

describe('humanReadableBarcode', () => {
  it('guard-splits an EAN-13 into digit / 6 / 6', () => {
    expect(humanReadableBarcode(VALID_EAN13, 'EAN13')).toBe('4 006381 333931');
  });

  it('prints a Code128 value plain, with no guard split', () => {
    expect(humanReadableBarcode('SKU-1234', 'CODE128')).toBe('SKU-1234');
  });

  it('trims surrounding whitespace either way', () => {
    expect(humanReadableBarcode(`  ${VALID_EAN13}  `, 'EAN13')).toBe('4 006381 333931');
  });
});

// ---------------------------------------------------------------------------
// Label plate geometry (review fix: the print page treated this bug's origin
// - a canvas-pixel floor - as millimetres, which forced an oversized font and
// squeezed the bars into a fraction of the plate; AC-S7-4/6).
// ---------------------------------------------------------------------------

describe('barcodePlateGeometry', () => {
  // A real plate size: the default the toolbar's "Add Barcode" inserts at.
  const WIDTH_MM = 40;
  const HEIGHT_MM = 22;

  it('bands the plate into strip / bars / human-readable, all in mm of plate', () => {
    const geo = barcodePlateGeometry(WIDTH_MM, HEIGHT_MM, true);

    expect(geo.stripHeight_mm).toBeCloseTo(22 * 0.18, 5); // 3.96
    expect(geo.humanHeight_mm).toBeCloseTo(22 * 0.16, 5); // 3.52
    expect(geo.barsY_mm).toBeCloseTo(geo.stripHeight_mm, 5);
    expect(geo.barsHeight_mm).toBeCloseTo(
      HEIGHT_MM - geo.stripHeight_mm - geo.humanHeight_mm,
      5,
    ); // 14.52
    expect(geo.barsX_mm).toBeCloseTo(40 * 0.06, 5); // 2.4
    expect(geo.barsWidth_mm).toBeCloseTo(40 * 0.88, 5); // 35.2
    expect(geo.cornerRadius_mm).toBeCloseTo(22 * 0.06, 5); // 1.32, min(w,h)
  });

  it('zeroes the strip band and its font when the strip is hidden', () => {
    const geo = barcodePlateGeometry(WIDTH_MM, HEIGHT_MM, false);

    expect(geo.stripHeight_mm).toBe(0);
    expect(geo.barsY_mm).toBe(0);
    expect(geo.stripFontSize_mm).toBe(0);
    // The bars band grows to fill the space the strip gave up.
    expect(geo.barsHeight_mm).toBeCloseTo(HEIGHT_MM - geo.humanHeight_mm, 5);
  });

  it('sizes font in mm of plate, well under the old 6mm-floor bug and never zero', () => {
    const geo = barcodePlateGeometry(WIDTH_MM, HEIGHT_MM, true);

    // strip band is 3.96mm; ratio-derived font (2.376mm) clears the 2mm floor,
    // so the floor is NOT what is driving the number - the old bug forced
    // every plate onto a fixed 6mm (~17pt) floor regardless of band size.
    expect(geo.stripFontSize_mm).toBeCloseTo(3.96 * 0.6, 5);
    expect(geo.stripFontSize_mm).toBeLessThan(6);
    expect(geo.humanFontSize_mm).toBeCloseTo(3.52 * 0.6, 5);
    expect(geo.humanFontSize_mm).toBeLessThan(6);
  });

  it('floors the font at 2mm of plate for a plate too small for the ratio', () => {
    const geo = barcodePlateGeometry(10, 6, true); // tiny plate: bands ~1mm

    expect(geo.stripFontSize_mm).toBe(2);
    expect(geo.humanFontSize_mm).toBe(2);
  });

  it('converts mm to pt at the fixed CSS factor', () => {
    expect(MM_TO_PT).toBeCloseTo(2.8346, 4);
  });
});
