/**
 * P6 - the search term the picker opens with.
 *
 * The customer prints OUR code inside THEIRS, so searching a product catalogue for
 * `BUI-HB-SRTWB7055` finds nothing and the picker opens on "No products match", which reads
 * as "the product does not exist". The seed is the same candidate the backend resolver
 * already tries (`_code_candidates`), so the two agree about what part of the printed code
 * is ours.
 */
import { describe, expect, it } from 'vitest';
import { productSearchSeed } from './DeliveryScheduleProductPicker';

describe('productSearchSeed', () => {
  it('strips the customer prefix off their code', () => {
    expect(productSearchSeed('BUI-HB-SRTWB7055')).toBe('SRTWB7055');
  });

  it('keeps a trailing part of the code that is part of the code', () => {
    // Not "RL": a two-letter suffix is a variant marker, not a product code, and it is
    // below the four characters the backend's own fuzzy probe will even consider.
    expect(productSearchSeed('BUI-HB-SRTWC8613-RL')).toBe('SRTWC8613-RL');
  });

  it('searches a code with no prefix as it is', () => {
    expect(productSearchSeed('SRTFV1001')).toBe('SRTFV1001');
  });

  it('asks for nothing when the column has no code at all', () => {
    expect(productSearchSeed(null)).toBe('');
    expect(productSearchSeed('   ')).toBe('');
  });
});
