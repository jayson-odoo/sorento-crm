/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): a stale tab never posts an older decision over a
 * newer save, and a saved decision that differs from AutoCount's pending suggestion is said.
 */
import { describe, expect, it } from 'vitest';
import { newerServerDraftKeys, suggestionMovedOf } from './confirmPreviewFresh';
import { annotationOf, type BoardChangeAnnotation } from './boardChangeAnnotations';
import type { PlanningChangeRow } from '../types/planningChange.types';
import type { BoardContribution, BoardDecision } from '../types/fulfilmentPlanning.types';

const draftAt = (key: string, savedAt: string) => ({
  key,
  draft: { decision: { verdict: 'approved' as const }, saved_by: 'Test Planner', saved_at: savedAt },
});

describe('newerServerDraftKeys', () => {
  const local = { a: { verdict: 'approved' as const }, b: { verdict: 'approved' as const } };

  it('names a key whose server draft was saved after the one this tab holds', () => {
    const held = new Map([['a', '2026-11-02T01:00:00Z']]);
    expect([...newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T02:00:00Z')])]).toEqual(['a']);
  });

  it('leaves the same or an older save alone', () => {
    const held = new Map([['a', '2026-11-02T02:00:00Z']]);
    expect(newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T02:00:00Z')]).size).toBe(0);
    expect(newerServerDraftKeys(local, held, [draftAt('a', '2026-11-02T01:00:00Z')]).size).toBe(0);
  });

  it('leaves a pre-mark, a key with no record and a key mid-write alone', () => {
    const held = new Map([['a', '2026-11-02T01:00:00Z']]);
    const later = [draftAt('a', '2026-11-02T02:00:00Z'), draftAt('b', '2026-11-02T02:00:00Z')];
    expect(
      newerServerDraftKeys({ a: { verdict: 'approved', preMarked: true } }, held, later).size,
    ).toBe(0);
    expect(newerServerDraftKeys(local, held, later, (key) => key === 'a').size).toBe(0);
    expect([...newerServerDraftKeys(local, held, later)]).toEqual(['a']);
  });
});

const contribution = {
  key: 'k',
  sources: [],
  fulfilment_location: 'BRW-BB',
} as unknown as BoardContribution;

const changed = (now: string | null, closed = false) =>
  ({ closed, now: { qty: '3', date: '2026-11-02', decision: now } }) as unknown as BoardChangeAnnotation;

const buy3: BoardDecision = { verdict: 'amended', buy_qty: '3' } as BoardDecision;

describe('suggestionMovedOf', () => {
  it('says the suggestion and what the planner keeps when they differ', () => {
    const moved = suggestionMovedOf(contribution, buy3, [changed('Use own location 3 from BRW-BB')]);
    expect(moved?.suggestion).toBe('Use own location 3 from BRW-BB');
    expect(moved?.kept).toMatch(/3/);
    expect(moved?.kept).not.toBe(moved?.suggestion);
  });

  it('says nothing when the saved decision reads as the suggestion', () => {
    const kept = suggestionMovedOf(contribution, buy3, [changed('Something else')])?.kept as string;
    expect(suggestionMovedOf(contribution, buy3, [changed(kept)])).toBeNull();
  });

  it('says nothing for a pre-mark, a rejection, or a line no change names', () => {
    const annotations = [changed('Use own location 3 from BRW-BB')];
    // A pre-mark that WOULD read differently (Buy 3 against the change's reserve) still says
    // nothing: it is the board's own suggestion, not a decision anybody saved.
    expect(
      suggestionMovedOf(
        contribution,
        { verdict: 'approved', preMarked: true, buy_qty: '3' } as BoardDecision,
        annotations,
      ),
    ).toBeNull();
    expect(suggestionMovedOf(contribution, { verdict: 'rejected' } as BoardDecision, annotations)).toBeNull();
    expect(suggestionMovedOf(contribution, buy3, [])).toBeNull();
    expect(suggestionMovedOf(contribution, buy3, [changed(null)])).toBeNull();
    expect(suggestionMovedOf(contribution, undefined, annotations)).toBeNull();
  });

  it('reads the latest change that still names a decision', () => {
    const moved = suggestionMovedOf(contribution, buy3, [
      changed('Use own location 1 from BRW-BB'),
      changed('Use own location 3 from BRW-BB'),
    ]);
    expect(moved?.suggestion).toBe('Use own location 3 from BRW-BB');
  });
});

/** A real change row, through the board's own `annotationOf` (review round 1, should-fix 2). */
function rowWith(composition: Record<string, unknown>): BoardChangeAnnotation {
  return annotationOf(
    {
      id: 'row-1',
      line_no: 10,
      so_line_no: 10,
      item_code: 'ZZT-ITEM-1',
      kind: 'date_moved',
      from: { qty: '3', required_date: '2026-09-28' },
      to: { qty: '3', required_date: '2026-11-02' },
      composition,
      applied_state: 'pending',
    } as unknown as PlanningChangeRow,
    'SO000001',
    'BRW-BB',
  );
}

const withIncomingSource = {
  ...contribution,
  sources: [{ kind: 'timely_spo', rung: 'incoming', qty: '3', location: 'BRW' }],
} as unknown as BoardContribution;

describe('suggestionMovedOf against a real change row', () => {
  it('an incoming share equal to the change reads as the same, wherever one side names a place', () => {
    const annotation = rowWith({ timely_spo_qty: '3', reserve: [], borrow: [], buy_qty: '0' });
    const saved = { verdict: 'amended', timely_spo_qty: '3', reserve: [], borrow: [], buy_qty: '0' } as BoardDecision;
    expect(suggestionMovedOf(withIncomingSource, saved, [annotation])).toBeNull();
  });

  it('a Buy equal to the change reads as the same', () => {
    const annotation = rowWith({ timely_spo_qty: '0', reserve: [], borrow: [], buy_qty: '3' });
    const saved = { verdict: 'amended', timely_spo_qty: '0', reserve: [], borrow: [], buy_qty: '3' } as BoardDecision;
    expect(suggestionMovedOf(contribution, saved, [annotation])).toBeNull();
  });

  it('a Buy the planner keeps against a change that now reserves is flagged', () => {
    const annotation = rowWith({
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-own', location: 'BRW-BB', qty: '3' }],
      borrow: [],
      buy_qty: '0',
    });
    const saved = { verdict: 'amended', timely_spo_qty: '0', reserve: [], borrow: [], buy_qty: '3' } as BoardDecision;
    const moved = suggestionMovedOf(contribution, saved, [annotation]);
    expect(moved).not.toBeNull();
    expect(moved?.kept).toContain('3');
    expect(moved?.suggestion).toContain('3');
  });
});

