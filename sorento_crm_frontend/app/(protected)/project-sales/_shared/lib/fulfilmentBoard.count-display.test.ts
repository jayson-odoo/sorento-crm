/**
 * PLAN-BATCH-COUNT-DISPLAY (owner ruling 21 Oct 2026 ~16:15 MYT, crew ruling (b)): Confirm (N) and
 * Saved (N) count only decisions someone made; the lines a pending AutoCount change retires are
 * one separate note, and a press with no decisions reads "Apply AutoCount change(s)", never an
 * enabled "Confirm (0)".
 */
import { describe, expect, it } from 'vitest';
import type {
  BoardContribution,
  BoardDraft,
} from '../types/fulfilmentPlanning.types';
import {
  autocountChangeNotes,
  autocountChangeSentence,
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

describe('the AutoCount change is one note per order (D2)', () => {
  it('lists the retired lines of each order with their item codes', () => {
    expect(autocountChangeNotes(contributions, draft)).toEqual([
      {
        salesOrderId: SO,
        soNumber: 'SO394881',
        count: 10,
        itemCodes: ['SRTWCX8840-S-RL'],
      },
    ]);
  });

  it('a line with a decision is not part of the note', () => {
    expect(autocountChangeNotes(cancels, draft)).toEqual([]);
  });
});

describe('the note sentence (D2-D5)', () => {
  const note = {
    count: 10,
    itemCodes: ['SRTWCX8840-S-RL'],
    createdAt: '2026-09-24T06:36:12',
  };

  it('on the board, beside decisions and on its own', () => {
    expect(autocountChangeSentence(note, 'board', true)).toBe(
      'Also applies the AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) are retired',
    );
    expect(autocountChangeSentence(note, 'board', false)).toBe(
      'Applies the AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) are retired',
    );
  });

  it('in Simulate and after Confirm', () => {
    expect(autocountChangeSentence(note, 'simulated', true)).toBe(
      'Would also apply the AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) would be retired',
    );
    expect(autocountChangeSentence(note, 'confirmed', true)).toBe(
      'Also applied the AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) were retired',
    );
  });

  it('one line, many item codes, and no batch date', () => {
    expect(
      autocountChangeSentence(
        { count: 1, itemCodes: ['CB110'], createdAt: null },
        'board',
        false,
      ),
    ).toBe(
      'Applies the pending AutoCount change: 1 old line (CB110) is retired',
    );
    expect(
      autocountChangeSentence(
        {
          count: 5,
          itemCodes: ['A', 'B', 'C', 'D', 'E'],
          createdAt: '2026-10-02T00:00:00',
        },
        'confirmed',
        false,
      ),
    ).toBe(
      'Applied the AutoCount change from 2 Oct: 5 old lines (A, B, C and 2 more) were retired',
    );
  });
});

describe('the Confirm button never offers an enabled Confirm (0) (crew ruling b)', () => {
  it('counts decisions when there are any', () => {
    expect(confirmButtonLabel(12, 1)).toBe('Confirm (12)');
    expect(confirmButtonLabel(12, 3)).toBe('Confirm (12)');
  });

  it('reads Apply AutoCount change(s) when only changes are pending', () => {
    expect(confirmButtonLabel(0, 1)).toBe('Apply AutoCount change');
    expect(confirmButtonLabel(0, 3)).toBe('Apply AutoCount changes (3 orders)');
  });

  it('control: nothing to do reads Confirm (0)', () => {
    expect(confirmButtonLabel(0, 0)).toBe('Confirm (0)');
  });
});
