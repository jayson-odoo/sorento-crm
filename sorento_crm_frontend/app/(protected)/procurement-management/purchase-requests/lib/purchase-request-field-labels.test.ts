/**
 * The default Update and Reply message quotes the document number, so it is one
 * of the surfaces the derived `-R{n}` suffix must reach (UAC N4/N5) - the
 * contact reading the message has to see the same number the screens and the
 * exported sheet show.
 *
 * The phrase is message text only. The stored number stays bare, and so does
 * the editable `request_number` input, so nothing suffixed can be submitted
 * back.
 */
import { describe, it, expect } from 'vitest';

import { purchaseRequestNumberReplyPhrase } from './purchase-request-field-labels';

describe('purchaseRequestNumberReplyPhrase', () => {
  it('carries the revision suffix for a purchase request', () => {
    expect(purchaseRequestNumberReplyPhrase('purchase_request', 'PR26-0332', 2)).toBe(
      'purchase request number PR26-0332-R2',
    );
  });

  it('carries the revision suffix for a sponsorship form', () => {
    expect(
      purchaseRequestNumberReplyPhrase('sponsorship_form', 'PSSF26-0326', 1),
    ).toBe('sponsorship form number PSSF26-0326-R1');
  });

  it('stays bare at revision 0', () => {
    expect(purchaseRequestNumberReplyPhrase('purchase_request', 'PR26-0332', 0)).toBe(
      'purchase request number PR26-0332',
    );
  });

  it('stays bare when the revision is unknown', () => {
    expect(purchaseRequestNumberReplyPhrase('purchase_request', 'PR26-0332')).toBe(
      'purchase request number PR26-0332',
    );
  });

  it('drops to the bare phrase when there is no number yet', () => {
    expect(purchaseRequestNumberReplyPhrase('sponsorship_form', null, 4)).toBe(
      'sponsorship form number',
    );
  });
});
