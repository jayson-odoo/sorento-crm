/**
 * PLAN-BATCH-HELD-CANCEL (owner ruling (a), 21 Oct 2026; UAC U1, U2): SO394881's shape. A pending
 * AutoCount change cancelled 10 old lines (the board shows them `cancelled`, no `cancelled_at`) and
 * added replacement lines; CS saved Cancel SO on 12 replacement lines the change NAMES. One press
 * applies the change and sends the 12 Cancel SO, so the counter, Saved and the body all name the
 * same 22 lines. Before the fix the 12 were held (`blocked_cancel`): Confirm (10), Saved (0), and
 * the panel posted nothing for the order.
 */
import { describe, expect, it } from 'vitest';
import type { BoardContribution, BoardDraft } from '../types/fulfilmentPlanning.types';
import {
  cancelledLinesFor,
  confirmDialogRowsFor,
  confirmLinesFor,
  confirmSummaryFor,
  pressPostsContribution,
} from './fulfilmentBoard';

const SO = 'pso-394881';

function row(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: `${SO}|1|RL-1|2026-12-08`,
    sales_order_id: SO,
    project_line_id: 'pl-1',
    so_number: 'SO394881',
    line_no: 1,
    item_code: 'RL-1',
    qty: '40',
    unplannable: false,
    cancelled: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    contested: false,
    covered: false,
    decision: null,
    locations: [],
    ...overrides,
  } as BoardContribution;
}

const CANCEL = {
  verdict: 'cancelled',
  reason: 'Customer replaced the order',
  reserve: [],
  borrow: [],
  timely_spo_qty: '0',
  buy_qty: '0',
} as unknown as BoardDraft[string];

// The 10 old lines the book cancelled (the change's `cancelled` rows).
const bookCancelled = [5, 14, 22, 30, 38, 46, 54, 62, 70, 78].map((lineNo) =>
  row({
    key: `${SO}|${lineNo}|RL-OLD|nodate`,
    project_line_id: `pl-${lineNo}`,
    line_no: lineNo,
    qty: '0',
    cancelled: true,
  }),
);
// 12 replacement lines the change names, Cancel SO saved on each.
const replacementLineNos = [82, 96, 112, 256, 272, 296, 480, 496, 512, 640, 656, 672];
const replacements = replacementLineNos.map((lineNo) =>
  row({ key: `${SO}|${lineNo}|RL-NEW|2026-12-08`, project_line_id: `pl-${lineNo}`, line_no: lineNo }),
);
// Lines an active decision covers and nobody touched (the board's "Confirmed" rows).
const covered = [1, 2, 3].map((lineNo) =>
  row({
    key: `${SO}|${lineNo}|RL-1|2026-12-08`,
    project_line_id: `pl-${lineNo}`,
    line_no: lineNo,
    covered: true,
    decision: { revision_no: 3 } as never,
  }),
);
const contributions = [...covered, ...bookCancelled, ...replacements];
const draft: BoardDraft = Object.fromEntries(replacements.map((line) => [line.key, CANCEL]));
const named = new Set([...bookCancelled, ...replacements].map((line) => line.key));
const blocked = new Set([SO]);
const options = { batchNamedKeys: named } as never;

describe('a saved Cancel SO the pending AutoCount change names rides in the same press (U2)', () => {
  it('is sent in cancelled_lines beside the batch, all 12', () => {
    expect(
      cancelledLinesFor(contributions, SO, draft, {
        batchBlocked: true,
        batchNamedKeys: named,
      } as never),
    ).toEqual(
      replacementLineNos.map((lineNo) => ({
        project_line_id: `pl-${lineNo}`,
        reason: 'Customer replaced the order',
      })),
    );
  });

  it('never composes a Cancel SO line into `lines`', () => {
    expect(confirmLinesFor(contributions, SO, draft)).toEqual([]);
  });

  it('the confirm dialog lists the 12 as Cancel SO and holds nothing back', () => {
    const dialog = confirmDialogRowsFor(contributions, draft, {
      currentUserName: 'Cyndi',
      openedAt: new Date('2026-10-21T00:00:00Z'),
      batchBlockedSalesOrderIds: blocked,
      batchNamedKeys: named,
    } as never);
    expect(dialog.rows.map((r) => r.composition)).toEqual(
      replacementLineNos.map(() => 'Cancel SO'),
    );
    expect(dialog.notPosted).toHaveLength(0);
    expect(dialog.cancelled).toHaveLength(10);
  });
});

describe('the counter offers exactly what the press does (U1)', () => {
  it('Confirm counts the 10 lines the change retires plus the 12 Cancel SO, on one order', () => {
    const summary = confirmSummaryFor(contributions, draft, blocked, options);
    expect(summary.orderCount).toBe(1);
    expect(summary.toConfirm).toBe(22);
  });

  it('Saved names the same 22 lines Confirm counts, never Saved (0) beside Confirm (N)', () => {
    const saved = contributions.filter((line) =>
      pressPostsContribution(line, draft[line.key], {
        batchBlocked: true,
        batchNamedKeys: named,
      } as never),
    );
    expect(saved.map((line) => line.line_no)).toEqual([
      ...bookCancelled.map((line) => line.line_no),
      ...replacementLineNos,
    ]);
    expect(saved).toHaveLength(confirmSummaryFor(contributions, draft, blocked, options).toConfirm);
  });

  it('control: a covered untouched line is neither saved nor counted', () => {
    expect(pressPostsContribution(covered[0], undefined, { batchBlocked: true } as never)).toBe(
      false,
    );
    expect(confirmSummaryFor(covered, {}, blocked, options).toConfirm).toBe(0);
  });
});

// The 12 SO394881 drafts are most likely AUTOMATIC: an AutoCount Cancel SO document cancelled the
// line and the ingest saved Transfer to Cancel SO on it (`propose_autocount_cancel`, source
// `autocount_cancel`, reason "AutoCount Cancel SO <doc>"). The line is cancelled in the book but
// still awaits the transfer (`awaitsCancelSo`). Any order with an open batch naming such a line
// was stuck the same way, so the rule is general, not SO394881's.
describe('an AutoCount Cancel SO draft on a line the pending change names rides in the press too', () => {
  const autocount = row({
    key: `${SO}|82|RL-NEW|2026-12-08`,
    project_line_id: 'pl-82',
    line_no: 82,
    cancelled: true,
    cancel_open_oi_rows: 2,
  } as never);
  const draft: BoardDraft = {
    [autocount.key]: {
      verdict: 'cancelled',
      reason: 'AutoCount Cancel SO CSO-0001',
      source: 'autocount_cancel',
    } as unknown as BoardDraft[string],
  };
  const namedAutocount = new Set([autocount.key]);

  it('is sent in cancelled_lines with its AutoCount reason, counted and Saved', () => {
    expect(
      cancelledLinesFor([autocount], SO, draft, {
        batchBlocked: true,
        batchNamedKeys: namedAutocount,
      } as never),
    ).toEqual([{ project_line_id: 'pl-82', reason: 'AutoCount Cancel SO CSO-0001' }]);
    expect(
      confirmSummaryFor([autocount], draft, blocked, { batchNamedKeys: namedAutocount } as never)
        .toConfirm,
    ).toBe(1);
    expect(
      pressPostsContribution(autocount, draft[autocount.key], {
        batchBlocked: true,
        batchNamedKeys: namedAutocount,
      } as never),
    ).toBe(true);
  });
});
