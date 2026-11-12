/**
 * OI-WHOLE-SO-CANCEL v2 (H2), red: the OI document status gains a "waiting_for_cs" word;
 * today anything that is not outstanding reads "Completed".
 */
import { describe, expect, it } from 'vitest';
import {
  orderInquiryHeaderStatusLabel,
  orderInquiryHeaderStatusVariant,
} from './orderInquiryHeaderStatus';

describe('H2: the OI header status reads Waiting for CS', () => {
  it('labels waiting_for_cs as "Waiting for CS", not "Completed"', () => {
    expect(orderInquiryHeaderStatusLabel('waiting_for_cs' as never)).toBe('Waiting for CS');
  });

  it('keeps Outstanding and Completed as they were', () => {
    expect(orderInquiryHeaderStatusLabel('outstanding')).toBe('Outstanding');
    expect(orderInquiryHeaderStatusLabel('completed')).toBe('Completed');
  });

  it('does not give a waiting document the neutral Completed tone', () => {
    expect(orderInquiryHeaderStatusVariant('waiting_for_cs' as never)).not.toBe('secondary');
  });
});
