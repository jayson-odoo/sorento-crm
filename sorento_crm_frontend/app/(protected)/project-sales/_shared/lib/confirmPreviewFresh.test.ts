/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): a stale tab never posts an older decision over a
 * newer save, and a saved decision that differs from AutoCount's pending suggestion is said.
 */
import { describe, expect, it } from 'vitest';
import { newerServerDraftKeys, suggestionMovedOf } from './confirmPreviewFresh';
import type { BoardChangeAnnotation } from './boardChangeAnnotations';
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
    expect(suggestionMovedOf(contribution, { verdict: 'approved', preMarked: true }, annotations)).toBeNull();
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
