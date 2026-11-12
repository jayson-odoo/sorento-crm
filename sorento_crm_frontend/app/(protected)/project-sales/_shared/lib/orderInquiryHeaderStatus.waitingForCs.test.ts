/**
 * OI-WHOLE-SO-CANCEL v2 (H2), changed by the owner ruling 12 Nov 22:55: a header with a line
 * waiting for CS reads plain "Outstanding"; the header has no "Waiting for CS" word. (The line
 * level keeps it.)
 */
import { describe, expect, it } from 'vitest';
import { orderInquiryHeaderStatusLabel } from './orderInquiryHeaderStatus';

describe('H2: the OI header status never reads Waiting for CS', () => {
  it('keeps Outstanding and Completed as they were', () => {
    expect(orderInquiryHeaderStatusLabel('outstanding')).toBe('Outstanding');
    expect(orderInquiryHeaderStatusLabel('completed')).toBe('Completed');
  });

  it('has no "Waiting for CS" header word, even for a status the server no longer sends', () => {
    expect(orderInquiryHeaderStatusLabel('waiting_for_cs' as never)).not.toBe('Waiting for CS');
  });
});
