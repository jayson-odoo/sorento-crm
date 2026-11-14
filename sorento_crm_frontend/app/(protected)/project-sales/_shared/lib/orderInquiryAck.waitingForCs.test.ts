/**
 * OI-WHOLE-SO-CANCEL v2 (AC-V2-5), red: the status text the OI screens print.
 * "Waiting for CS" while the row's SO line has an unapplied change (whatever the ack
 * state), "SO cancelled" for a cancelled / deleted header, today's text otherwise.
 */
import { describe, expect, it } from 'vitest';
import { ackStatusText } from './orderInquiryAck';

type Row = Parameters<typeof ackStatusText>[0] & {
  waiting_for_cs?: boolean;
  so_cancelled?: boolean;
};
const row = (over: Partial<Row>): Row => ({ ack_state: 'awaiting', qty: '10', ...over });

describe('AC-V2-5: ackStatusText', () => {
  it.each(['awaiting', 'acknowledged', 'changed', 'rejected'] as const)(
    'reads "Waiting for CS" for a waiting %s row',
    (ack) => {
      expect(ackStatusText(row({ ack_state: ack, waiting_for_cs: true }))).toBe('Waiting for CS');
    },
  );

  it('reads "Waiting for CS" even when the SO is also cancelled (waiting wins)', () => {
    expect(ackStatusText(row({ waiting_for_cs: true, so_cancelled: true }))).toBe('Waiting for CS');
  });

  it('reads "SO cancelled" for a cancelled SO that is not waiting', () => {
    expect(ackStatusText(row({ so_cancelled: true, waiting_for_cs: false }))).toBe('SO cancelled');
  });

  it('leaves today\'s text alone for a row that is neither', () => {
    expect(ackStatusText(row({ waiting_for_cs: false, so_cancelled: false }))).toBe('To order');
    expect(ackStatusText(row({ ack_state: 'acknowledged' }))).toBe('Done');
  });
});
