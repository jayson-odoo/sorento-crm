/**
 * PLAN-BATCH-COUNT-DISPLAY (owner ruling 21 Oct 2026 ~16:15 MYT, crew ruling (b)): Confirm (N) and
 * Saved (N) count only decisions someone made; the lines a pending AutoCount change retires are
 * not counted until saved. F2 12/13 Nov (owner: "follow the path of Decide Confirm like normal
 * fulfilment planning"): a cancel is saved like any change before Confirm, there is no separate
 * "Applies the AutoCount change" note and the button is always "Confirm (N)", never "Apply
 * AutoCount change".
 */
import { describe, expect, it } from 'vitest';
import type {
  BoardContribution,
  BoardDraft,
} from '../types/fulfilmentPlanning.types';
import {
  autocountChangeNotes,
  confirmButtonLabel,
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
  reason: 'AutoCount Cancel SO CSO-0001',
  source: 'autocount_cancel',
} as unknown as BoardDraft[string];

const retired = [5, 14, 22, 30, 38, 46, 54, 62, 70, 78].map((lineNo) =>
  row({
    key: `${SO}|${lineNo}|SRTWCX8840-S-RL|nodate`,
    project_line_id: `pl-${lineNo}`,
    line_no: lineNo,
    item_code: 'SRTWCX8840-S-RL',
    qty: '0',
    cancelled: true,
  }),
);
const cancelLineNos = [
  82, 96, 112, 256, 272, 296, 480, 496, 512, 640, 656, 672,
];
const cancels = cancelLineNos.map((lineNo) =>
  row({
    key: `${SO}|${lineNo}|RL-NEW|2026-12-08`,
    project_line_id: `pl-${lineNo}`,
    line_no: lineNo,
  }),
);
const contributions = [...retired, ...cancels];
const draft: BoardDraft = Object.fromEntries(
  cancels.map((line) => [line.key, CANCEL]),
);
const named = new Set(contributions.map((line) => line.key));
const options = { batchNamedKeys: named } as never;

describe('Confirm and Saved count decisions only (D1)', () => {
  it('SO394881 reads 12, not 22: the 10 retired lines are not counted', () => {
    expect(
      confirmSummaryFor(contributions, draft, new Set([SO]), options).toConfirm,
    ).toBe(12);
  });

  it('Saved names the 12 Cancel SO lines and none of the retired lines', () => {
    const saved = contributions.filter((line) =>
      pressPostsContribution(line, draft[line.key], {
        batchBlocked: true,
        batchNamedKeys: named,
      } as never),
    );
    expect(saved.map((line) => line.line_no)).toEqual(cancelLineNos);
  });
});

describe('there is no AutoCount change note any more (F2 12/13 Nov)', () => {
  it('retired lines and undecided cancels raise no note', () => {
    expect(autocountChangeNotes(contributions, draft)).toEqual([]);
    expect(autocountChangeNotes(contributions, {})).toEqual([]);
  });
});

describe('the Confirm button never offers an enabled Confirm (0) (crew ruling b)', () => {
  it('counts decisions when there are any', () => {
    expect(confirmButtonLabel(12, 1)).toBe('Confirm (12)');
    expect(confirmButtonLabel(12, 3)).toBe('Confirm (12)');
  });

  it('always reads Confirm (N), never Apply AutoCount change(s), when only changes are pending', () => {
    expect(confirmButtonLabel(0, 1)).toBe('Confirm (0)');
    expect(confirmButtonLabel(0, 3)).toBe('Confirm (0)');
  });

  it('control: nothing to do reads Confirm (0)', () => {
    expect(confirmButtonLabel(0, 0)).toBe('Confirm (0)');
  });
});
