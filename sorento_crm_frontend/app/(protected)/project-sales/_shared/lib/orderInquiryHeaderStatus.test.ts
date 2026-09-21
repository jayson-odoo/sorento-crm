/**
 * AC-HL-04 / AC-FE-01: the OI header's status Badge mapping - outstanding is the
 * warning tone, completed is neutral (secondary) - is shared by the Documents list and
 * the detail page's own header card, so it lives and is pinned in exactly one place.
 */
import { describe, expect, it } from 'vitest';
import {
  orderInquiryHeaderStatusLabel,
  orderInquiryHeaderStatusVariant,
} from './orderInquiryHeaderStatus';

describe('orderInquiryHeaderStatusVariant (AC-HL-04)', () => {
  it('outstanding maps to the warning tone', () => {
    expect(orderInquiryHeaderStatusVariant('outstanding')).toBe('warning');
  });

  it('completed maps to the neutral (secondary) tone, not a celebratory one', () => {
    expect(orderInquiryHeaderStatusVariant('completed')).toBe('secondary');
  });
});

describe('orderInquiryHeaderStatusLabel', () => {
  it('reads "Outstanding" / "Completed"', () => {
    expect(orderInquiryHeaderStatusLabel('outstanding')).toBe('Outstanding');
    expect(orderInquiryHeaderStatusLabel('completed')).toBe('Completed');
  });
});
