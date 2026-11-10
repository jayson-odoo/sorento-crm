import { describe, expect, it } from 'vitest';
import { orderInquiryMainAction } from './orderInquiryMainAction';

// UIUX-QUICK-WINS item 1: the OI detail header shows at most ONE filled button, the one
// the document's state is waiting for (DESIGN-LANGUAGE.md section 6, one CTA per page).
describe('orderInquiryMainAction', () => {
  const base = { showConfirm: true, confirmDisabled: false, showReserve: true, stagedCount: 0 };

  it('Confirm is the main action while lines wait to be confirmed and nothing is staged', () => {
    expect(orderInquiryMainAction(base)).toBe('confirm');
  });

  it('Reserve is the main action once a reserve is staged', () => {
    expect(orderInquiryMainAction({ ...base, stagedCount: 2 })).toBe('reserve');
  });

  it('Reserve is the main action when there is nothing left to confirm', () => {
    expect(orderInquiryMainAction({ ...base, confirmDisabled: true })).toBe('reserve');
  });

  it('the only button shown is the main one', () => {
    expect(orderInquiryMainAction({ ...base, showReserve: false, stagedCount: 3 })).toBe('confirm');
    expect(orderInquiryMainAction({ ...base, showConfirm: false })).toBe('reserve');
  });

  it('nothing shown, no main action', () => {
    expect(orderInquiryMainAction({ ...base, showConfirm: false, showReserve: false })).toBeNull();
  });
});
