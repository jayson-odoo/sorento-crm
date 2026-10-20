/**
 * OI-SPLIT-GUIDE (UAC F32, F33): the REMARK a Confirm sends for a covered line.
 * Clearing a confirmed remark on an Approve must post `remark: ""` (the server's only way to clear
 * it: a line that sends none keeps it); an opaque stored draft with `remark: null` (an API
 * client) is treated like no remark, never a crash.
 */
import { describe, expect, it } from 'vitest';
import type { BoardContribution, BoardDecision } from '../types/fulfilmentPlanning.types';
import { confirmLinesFor, remarkFor } from './fulfilmentBoard';
import { buildBoard, type BoardDemandLine } from './__testsupport__/boardFixture';

const DECISION = {
  revision_no: 3,
  confirmed_at: '2026-09-16T02:00:00',
  timely_spo_qty: '0',
  reserve: [],
  borrow: [],
  buy_qty: '10',
};

function confirmedContribution(confirmedRemark: string | null): BoardContribution {
  const line = {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'A CUSTOMER SDN BHD',
    project_sales_order_id: 'pso-1',
    project_line_id: 'pl-1-1',
    line_no: 1,
    item_code: 'ITEM-1',
    qty: '10',
    required_date: '2026-09-20',
    fulfilment_location: 'BRW-IB',
    priority: null,
    decision: DECISION,
  } as BoardDemandLine;
  const board = buildBoard([line], { today: '2026-09-17' });
  const c = board.cells.flatMap((cell) => cell.contributions)[0] as BoardContribution;
  return { ...c, confirmed_remark: confirmedRemark } as BoardContribution;
}

const approved = (extra: Partial<BoardDecision> = {}) =>
  ({ verdict: 'approved', ...extra }) as BoardDecision;

describe('clearing a confirmed remark on a covered Approve', () => {
  it('posts remark "" (not missing) when the saved draft cleared it', () => {
    const c = confirmedContribution('SITE HOLD');
    const lines = confirmLinesFor([c], 'so-1', { [c.key]: approved({ remark: '' }) });
    expect(lines).toHaveLength(1);
    expect(lines[0].remark).toBe('');
  });

  it('pin: an Approve with no remark carries the confirmed one', () => {
    const c = confirmedContribution('SITE HOLD');
    const lines = confirmLinesFor([c], 'so-1', { [c.key]: approved() });
    expect(lines[0].remark).toBe('SITE HOLD');
  });

  it('pin: a typed remark wins', () => {
    const c = confirmedContribution('SITE HOLD');
    const lines = confirmLinesFor([c], 'so-1', { [c.key]: approved({ remark: ' NEW WORDS ' }) });
    expect(lines[0].remark).toBe('NEW WORDS');
  });
});

describe('remarkFor is null-safe', () => {
  it('a stored draft decision with remark null does not throw and falls back to the confirmed remark', () => {
    const c = confirmedContribution('SITE HOLD');
    const decision = { verdict: 'approved', remark: null } as unknown as BoardDecision;
    expect(() => remarkFor(c, decision)).not.toThrow();
    expect(remarkFor(c, decision)).toBe('SITE HOLD');
  });

  it('remark null and nothing confirmed sends nothing', () => {
    const c = confirmedContribution(null);
    const decision = { verdict: 'approved', remark: null } as unknown as BoardDecision;
    expect(remarkFor(c, decision)).toBeUndefined();
  });
});
