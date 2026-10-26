/**
 * FULFIL-SO-REMARK-CHANGES (owner, 26 Oct 2026, R1): which lines of a press are a CHANGE, making
 * their order's Remark required. Every kind on the card's "A change" list, one test each, so none
 * can quietly fall back to optional; and the lines an AutoCount-change-only press retires (R3).
 *
 * Card: `documentation/plans/scm/CARD-fulfil-so-remark-changes-27oct.md`.
 */
import { describe, expect, it } from 'vitest';
import type { BoardContribution, BoardDraft } from '../types/fulfilmentPlanning.types';
import { autocountChangeLinesByOrder, isChangeLine } from './fulfilmentBoard';

const SO = 'so-zzt';

function row(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: `${SO}|1|ZZT-1|2026-12-08`,
    sales_order_id: SO,
    project_line_id: 'pl-1',
    so_number: 'SO000001',
    line_no: 1,
    item_code: 'ZZT-1',
    qty: '10',
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

const CONFIRMED = { covered: true, decision: { revision_no: 3 } as never };

function verdict(kind: string, extra: Record<string, unknown> = {}): BoardDraft[string] {
  return {
    verdict: kind,
    reserve: [],
    borrow: [],
    timely_spo_qty: '0',
    buy_qty: '10',
    ...extra,
  } as unknown as BoardDraft[string];
}

const draftOf = (line: BoardContribution, decision: BoardDraft[string]): BoardDraft => ({
  [line.key]: decision,
});

describe('isChangeLine', () => {
  it('a brand-new line first decided is not a change', () => {
    const line = row();
    expect(isChangeLine(line, draftOf(line, verdict('approved')))).toBe(false);
  });

  it('a re-approve of a confirmed line is a change (it posts the current suggestion)', () => {
    const line = row(CONFIRMED);
    expect(isChangeLine(line, draftOf(line, verdict('approved')))).toBe(true);
  });

  it('an Amend of a confirmed line is a change', () => {
    const line = row(CONFIRMED);
    const amend = verdict('amended', { amend_reason: 'Site cut.', buy_qty: '8' });
    expect(isChangeLine(line, draftOf(line, amend))).toBe(true);
  });

  it('a line posted over an order inquiry purchasing holds (covered, no decision) is a change', () => {
    const line = row({ covered: true, decision: null });
    expect(isChangeLine(line, draftOf(line, verdict('approved')))).toBe(true);
  });

  it('a withdrawal of a confirmed line is a change', () => {
    const line = row(CONFIRMED);
    expect(isChangeLine(line, draftOf(line, verdict('rejected', { reason: 'ZZT gone' })))).toBe(true);
  });

  it('a Transfer to Cancel SO is a change', () => {
    const line = row();
    expect(isChangeLine(line, draftOf(line, verdict('cancelled', { reason: 'ZZT gone' })))).toBe(
      true,
    );
  });

  it('a book-cancelled line the press retires is a change', () => {
    const line = row({ cancelled: true, qty: '0' });
    expect(isChangeLine(line, {})).toBe(true);
  });

  it('a split edit is a change', () => {
    const line = row({ ...CONFIRMED, split_edited: true } as Partial<BoardContribution>);
    expect(isChangeLine(line, {})).toBe(true);
  });
});

describe('autocountChangeLinesByOrder', () => {
  const retired = row({ key: `${SO}|2|ZZT-2|nodate`, project_line_id: 'pl-2', cancelled: true });

  it('lists a book-cancelled line on an order with a pending AutoCount change', () => {
    const out = autocountChangeLinesByOrder([row(), retired], {}, new Set([SO]));
    expect(out.get(SO)?.map((line) => line.project_line_id)).toEqual(['pl-2']);
  });

  it('lists nothing for an order with no pending change: the press would not retire it', () => {
    expect(autocountChangeLinesByOrder([retired], {}, new Set()).size).toBe(0);
  });

  it('leaves out a line still waiting for its Transfer to Cancel SO', () => {
    const waiting = { ...retired, cancel_open_oi_rows: 2 } as BoardContribution;
    expect(autocountChangeLinesByOrder([waiting], {}, new Set([SO])).size).toBe(0);
  });
});
