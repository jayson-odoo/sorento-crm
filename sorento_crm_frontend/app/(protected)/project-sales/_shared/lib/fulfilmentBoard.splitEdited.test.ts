/**
 * OI-SPLIT-VIEW (UAC A2): `BoardContribution.split_edited` is counted once per line in
 * `confirmSummaryFor` / `plannedLineCount`, and a split-edited line admits its order to the
 * press even with no verdict staged. Red until the build reads the flag.
 *
 * Two cases pin behaviour that already holds (named "pins today"): the same line without the
 * flag counts 0, and a line with a staged verdict counts 1 whether or not the flag is set.
 */
import { describe, expect, it } from 'vitest';
import type { BoardContribution } from '../types/fulfilmentPlanning.types';
import { confirmLinesFor, confirmSummaryFor, plannedLineCount, splitEditsToConfirm } from './fulfilmentBoard';
import { buildBoard, type BoardDemandLine } from './__testsupport__/boardFixture';

const TODAY = '2026-09-17';

const DECISION = {
  revision_no: 3,
  confirmed_at: '2026-09-16T02:00:00',
  timely_spo_qty: '0',
  reserve: [],
  borrow: [],
  buy_qty: '10',
};

function demand(lineNo: number, overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'A CUSTOMER SDN BHD',
    project_sales_order_id: 'pso-1',
    project_line_id: `pl-1-${lineNo}`,
    line_no: lineNo,
    item_code: `ITEM-${lineNo}`,
    qty: '10',
    required_date: '2026-09-20',
    fulfilment_location: 'BRW-IB',
    priority: null,
    decision: DECISION,
    ...overrides,
  } as BoardDemandLine;
}

function contributionsOf(lines: BoardDemandLine[], splitEdited: number[] = []): BoardContribution[] {
  const board = buildBoard(lines, { today: TODAY });
  return board.cells
    .flatMap((cell) => cell.contributions)
    .map((c) => (splitEdited.includes(c.line_no) ? { ...c, split_edited: true } : c)) as BoardContribution[];
}

const keyOf = (all: BoardContribution[], lineNo: number) => all.find((c) => c.line_no === lineNo)!.key;

describe('a split-edited line counts in the confirm summary (A2)', () => {
  it('a covered line with no verdict and no split edit counts 0 (pins today)', () => {
    const all = contributionsOf([demand(1)]);
    expect(confirmSummaryFor(all, {}).toConfirm).toBe(0);
  });

  it('a covered line with a saved split edit and no verdict counts 1 and admits its order', () => {
    const all = contributionsOf([demand(1)], [1]);
    const summary = confirmSummaryFor(all, {});
    expect(summary.toConfirm).toBe(1);
    expect(summary.orderCount).toBe(1);
    expect(plannedLineCount(all, 'so-1', {})).toBe(1);
  });

  it('with a staged verdict as well it still counts once, not twice', () => {
    const all = contributionsOf([demand(1)], [1]);
    const draft = { [keyOf(all, 1)]: { verdict: 'approved' as const } };
    expect(confirmSummaryFor(all, draft).toConfirm).toBe(1);
    expect(plannedLineCount(all, 'so-1', draft)).toBe(1);
  });

  it('a verdict line alone counts 1 whether or not the flag is set (pins today)', () => {
    const plain = contributionsOf([demand(1)]);
    const flagged = contributionsOf([demand(1)], [1]);
    const draft = { [keyOf(plain, 1)]: { verdict: 'approved' as const } };
    expect(confirmSummaryFor(plain, draft).toConfirm).toBe(1);
    expect(confirmSummaryFor(flagged, draft).toConfirm).toBe(1);
  });

  it('counts each split-edited line of an order once: two flagged lines read 2', () => {
    const all = contributionsOf([demand(1), demand(2)], [1, 2]);
    expect(confirmSummaryFor(all, {}).toConfirm).toBe(2);
  });

  it('a split-edited line beside an approved one reads 2, not 3', () => {
    const all = contributionsOf([demand(1), demand(2)], [1]);
    const draft = { [keyOf(all, 2)]: { verdict: 'approved' as const } };
    expect(confirmSummaryFor(all, draft).toConfirm).toBe(2);
  });

  it('a split-edited line cannot be unticked: excluding its key still counts it (A10)', () => {
    const all = contributionsOf([demand(1)], [1]);
    expect(
      confirmSummaryFor(all, {}, new Set(), { excludeKeys: new Set([keyOf(all, 1)]) }).toConfirm,
    ).toBe(1);
  });

  it('a split-edited line posts no body line of its own (the server applies it)', () => {
    const all = contributionsOf([demand(1)], [1]);
    expect(confirmLinesFor(all, 'so-1', {})).toEqual([]);
  });
});

describe('review round 3 (UAC A12): an order carrying a pending AutoCount batch still counts a split edit', () => {
  const BLOCKED = new Set(['so-1']);

  it('a split-edited line of a batch-blocked order counts 1 and admits its order', () => {
    const all = contributionsOf([demand(1)], [1]);
    const summary = confirmSummaryFor(all, {}, BLOCKED);
    expect(summary.toConfirm).toBe(1);
    expect(summary.orderCount).toBe(1);
    expect(plannedLineCount(all, 'so-1', {}, BLOCKED)).toBe(1);
  });

  it('is listed in the split edits to confirm', () => {
    const all = contributionsOf([demand(1)], [1]);
    expect(splitEditsToConfirm(all, {}, BLOCKED).map((c) => c.line_no)).toEqual([1]);
  });

  it('a line the batch names pending is still never counted as a split edit (A9)', () => {
    const all = contributionsOf([demand(1), demand(2)], [1, 2]);
    const named = new Set([keyOf(all, 2)]);
    const summary = confirmSummaryFor(all, {}, BLOCKED, { batchNamedKeys: named });
    expect(summary.toConfirm).toBe(1);
  });
});
