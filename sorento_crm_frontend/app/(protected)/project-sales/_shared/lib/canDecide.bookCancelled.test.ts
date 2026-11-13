/** OI-WHOLE-SO-CANCEL: a book-cancelled line can be ticked and decided. */
import { describe, expect, it } from 'vitest';
import { canDecide } from './boardAmend';
import type { BoardContribution } from '../types/fulfilmentPlanning.types';

function line(over: Record<string, unknown> = {}): BoardContribution {
  return {
    key: 'so-1:line-10',
    sales_order_id: 'so-1',
    so_number: 'SO900001',
    line_no: 10,
    item_code: 'CB110',
    qty: '0',
    unplannable: false,
    cancelled: false,
    cancelled_at: null,
    pending_change_batch_id: null,
    ...over,
  } as unknown as BoardContribution;
}

describe('canDecide and book-cancelled lines', () => {
  it('is true for a book-cancelled line', () => {
    expect(canDecide(line({ cancelled: true, pending_change_batch_id: 'b1' }))).toBe(true);
  });

  it('guard: false for a plain cancelled line with no pending batch and no open OI rows', () => {
    expect(canDecide(line({ cancelled: true }))).toBe(false);
  });

  it('guard: false for an unplannable line, even if book-cancelled', () => {
    expect(
      canDecide(line({ unplannable: true, cancelled: true, pending_change_batch_id: 'b1' })),
    ).toBe(false);
  });
});
