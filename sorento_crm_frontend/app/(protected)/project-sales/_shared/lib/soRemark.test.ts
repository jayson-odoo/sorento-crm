/**
 * FULFIL-SO-REMARK (AC-5, AC-6, card cases): the default SO remark and the line-label rule,
 * mirrored from the backend rules module so the Confirm guide prefills what the email prints.
 * Red until `soRemark.ts` exists.
 */
import { describe, expect, it } from 'vitest';

import { defaultSoRemark, shouldLabelMockupLines } from './soRemark';

describe('defaultSoRemark (AC-5)', () => {
  it('the remark type wins over mockup lines', () => {
    expect(defaultSoRemark('Sponsorship', [true])).toBe('Sponsorship');
    expect(defaultSoRemark('Purchase Request', [true, false])).toBe('Purchase Request');
  });

  it('Mockup when any chosen line is a mockup line and there is no remark type', () => {
    expect(defaultSoRemark(null, [false, true, false])).toBe('Mockup');
    expect(defaultSoRemark(undefined, [true])).toBe('Mockup');
  });

  it('blank otherwise', () => {
    expect(defaultSoRemark(null, [false, false])).toBe('');
    expect(defaultSoRemark(null, [])).toBe('');
  });

  it('SO419417: all 24 chosen -> Mockup, only the 3 -> Mockup, only the 21 -> blank', () => {
    expect(defaultSoRemark(null, [...Array(3).fill(true), ...Array(21).fill(false)])).toBe('Mockup');
    expect(defaultSoRemark(null, Array(3).fill(true))).toBe('Mockup');
    expect(defaultSoRemark(null, Array(21).fill(false))).toBe('');
  });
});

describe('shouldLabelMockupLines (AC-6)', () => {
  it('labels only when the chosen lines mix mockup and non-mockup', () => {
    expect(shouldLabelMockupLines([true, false])).toBe(true);
    expect(shouldLabelMockupLines([true, true])).toBe(false);
    expect(shouldLabelMockupLines([false, false])).toBe(false);
    expect(shouldLabelMockupLines([])).toBe(false);
  });
});
