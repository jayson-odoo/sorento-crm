/**
 * OI-WHOLE-SO-CANCEL F2 (owner 00:06), red: a book-cancelled line is DECIDED like any other
 * pending change. A saved cancel counts in Confirm (N); the Confirm button is ALWAYS
 * "Confirm (N)" (never "Apply AutoCount change(s)"); a cancel nobody saved is not counted and
 * never turns the press into the apply-only path.
 */
import { describe, expect, it } from 'vitest';
import { buildBoard } from './__testsupport__/boardFixture';
import { confirmButtonLabel, confirmSummaryFor } from './fulfilmentBoard';

const TODAY = '2026-08-18';

function cancelledContribution() {
  const board = buildBoard(
    [
      {
        sales_order_id: 'so-a',
        so_number: 'SO403340',
        customer_name: 'ZZT CUSTOMER',
        line_no: 1,
        item_code: 'WESERP10B',
        qty: '10',
        required_date: '2026-09-04',
        fulfilment_location: 'BRW-BB',
        priority: null,
      },
    ],
    { today: TODAY, freeStock: {}, granularity: 'week' },
  );
  return {
    ...board.contributions[0],
    qty: '0',
    cancelled: true,
    pending_change_batch_id: 'b1',
  } as never;
}

describe('F2: the Confirm button is always Confirm (N)', () => {
  it('never reads Apply AutoCount change(s), however many orders hold only changes', () => {
    expect(confirmButtonLabel(0, 1)).toBe('Confirm (0)');
    expect(confirmButtonLabel(0, 3)).toBe('Confirm (0)');
  });

  it('keeps counting decisions', () => {
    expect(confirmButtonLabel(12, 1)).toBe('Confirm (12)');
  });
});

describe('F2: a cancelled line is counted once saved', () => {
  it('counts nothing while the cancel is unsaved, and is not an apply-only change', () => {
    const summary = confirmSummaryFor([cancelledContribution()], {}, new Set());
    expect(summary.toConfirm).toBe(0);
    expect(summary.changed).toBe(0);
  });

  it('counts the saved cancel in Confirm (N)', () => {
    const contribution = cancelledContribution() as { key: string };
    const summary = confirmSummaryFor(
      [contribution as never],
      { [contribution.key]: { verdict: 'approved' } } as never,
      new Set(),
    );
    expect(summary.toConfirm).toBe(1);
    expect(summary.changed).toBe(0);
  });
});
