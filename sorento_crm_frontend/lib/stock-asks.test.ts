/**
 * REFER-SALESMAN (AC-RS21): the shared words for the two branches every refer reply now
 * records, beside the four stock-quantity branches.
 */
import { describe, expect, it } from 'vitest';
import { BRANCH_LABEL, BRANCH_VARIANT, SKIP_REASON_LABEL, notifiedLabel } from '@/lib/stock-asks';

describe('stock ask branch words', () => {
  it('labels every branch the backend writes', () => {
    expect(BRANCH_LABEL).toEqual({
      too_big: 'Too big',
      in_stock: 'In stock',
      incoming: 'Incoming',
      no_incoming: 'No stock, no incoming',
      incoming_eta: 'Incoming ETA',
      referred: 'Referred',
    });
    for (const branch of Object.keys(BRANCH_LABEL)) {
      expect(BRANCH_VARIANT[branch], branch).toBeTruthy();
    }
  });

  it('explains the not-notified reason for every branch that never notifies', () => {
    expect(SKIP_REASON_LABEL.not_notified_branch).toBe('This kind of answer does not notify the salesman');
    expect(notifiedLabel({ notified_agent: false, notify_skip_reason: 'not_notified_branch' })).toMatchObject({
      label: 'Not sent',
      title: 'This kind of answer does not notify the salesman',
    });
  });
});
