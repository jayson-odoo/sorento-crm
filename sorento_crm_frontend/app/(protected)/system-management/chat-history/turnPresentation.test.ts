/**
 * S2b Phase 2 test-first: pure-function coverage for `turnPresentation.ts` (AC-251,
 * AC-252, AC-254). Like `TurnPanel.test.tsx`, this locks Phase 1 behaviour that already
 * ships rather than red-then-green on its own - no test file existed for this module
 * before this one.
 */
import { describe, it, expect } from 'vitest';
import {
  buildTimeline,
  canRetry,
  formatMs,
  laneWords,
  memoryChips,
  shortTurnId,
  stageLabel,
  turnDuration,
  turnHeadline,
} from './turnPresentation';
import type { ChatbotTurn, TurnTraceRecord } from './types/chatbotTurn.types';

function record(over: Partial<TurnTraceRecord> = {}): TurnTraceRecord {
  return {
    stage: 'received',
    status: 'ok',
    started_at: '2026-09-05T06:00:00.000Z',
    ms: 100,
    summary: 'ok',
    why: 'ok',
    facts: {},
    error: null,
    raw: null,
    ...over,
  };
}

function turn(over: Partial<ChatbotTurn> = {}): ChatbotTurn {
  return {
    id: 'ZZT-turn',
    contact_respond_id: 'ZZT-contact',
    message_id: null,
    status: 'done',
    stage: null,
    branch_kind: null,
    attempt: 1,
    is_test: false,
    created_at: '2026-09-05T06:00:00.000Z',
    finished_at: null,
    trace: [],
    response: null,
    ...over,
  };
}

describe('turnHeadline (AC-251)', () => {
  it('names the failed stage on a failed turn', () => {
    expect(turnHeadline(turn({ status: 'failed', stage: 'access' }))).toEqual({
      word: 'Failed at Access',
      tone: 'failed',
    });
  });

  it('falls back to Received when a failed turn has no stage recorded', () => {
    expect(turnHeadline(turn({ status: 'failed', stage: null }))).toEqual({
      word: 'Failed at Received',
      tone: 'failed',
    });
  });

  it('is Answered for a plain business_query done turn', () => {
    expect(turnHeadline(turn({ status: 'done', branch_kind: 'business_query' })).word).toBe(
      'Answered',
    );
  });

  it('is Escalated for out_of_scope', () => {
    expect(turnHeadline(turn({ status: 'done', branch_kind: 'out_of_scope' })).word).toBe(
      'Escalated',
    );
  });

  it('is pending while the turn is still running or delegated', () => {
    expect(turnHeadline(turn({ status: 'processing' })).tone).toBe('pending');
    expect(turnHeadline(turn({ status: 'delegated' })).tone).toBe('pending');
  });
});

describe('laneWords / stageLabel', () => {
  it('says Lane not reached for a null branch_kind', () => {
    expect(laneWords(null)).toBe('Lane not reached');
  });

  it('humanises an off-timeline failure stage', () => {
    expect(stageLabel('casual_llm')).toBe('Small talk');
    expect(stageLabel('queued')).toBe('Queue');
  });
});

describe('buildTimeline (AC-252)', () => {
  it('collapses everything after the failed stage into one not-reached row', () => {
    const t = turn({
      status: 'failed',
      trace: [
        record({ stage: 'received' }),
        record({ stage: 'understood', status: 'failed', error: 'boom' }),
      ],
    });
    const rows = buildTimeline(t);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toMatchObject({ kind: 'stage', label: 'Received' });
    expect(rows[1]).toMatchObject({ kind: 'stage', label: 'Understood' });
    expect(rows[2].kind).toBe('not-reached');
    if (rows[2].kind === 'not-reached') {
      expect(rows[2].labels).toEqual([
        'Access',
        'Routed',
        'Looked up',
        'Replied',
        'Remembered',
        'Sent',
      ]);
    }
  });

  it('adds no not-reached row on a done turn with a short trace (the lane legitimately skipped stages)', () => {
    const t = turn({
      status: 'done',
      branch_kind: 'clarify_menu',
      trace: [record({ stage: 'received' }), record({ stage: 'understood' })],
    });
    expect(buildTimeline(t)).toHaveLength(2);
  });

  it('inserts the not-reached row right after the failed row, not at the end (sent can still run on a failed turn)', () => {
    const t = turn({
      status: 'failed',
      trace: [
        record({ stage: 'received' }),
        record({ stage: 'understood', status: 'failed', error: 'boom' }),
        record({ stage: 'sent' }),
      ],
    });
    const rows = buildTimeline(t);
    const kinds = rows.map((r) => r.kind);
    expect(kinds).toEqual(['stage', 'stage', 'not-reached', 'stage']);
  });
});

describe('memoryChips (AC-254)', () => {
  it('classifies kept / new / cleared and sorts kept before new before cleared', () => {
    const chips = memoryChips(
      record({
        stage: 'remembered',
        raw: {
          before: { domain_hint: 'inventory', pending: { kind: 'x' }, access_levels: ['dealer'] },
          after: { domain_hint: 'inventory', entities: [{ raw: 'x' }] },
        },
      }),
    );
    expect(chips.map((c) => c.kind)).toEqual(['kept', 'new', 'cleared', 'cleared']);
    const kept = chips.find((c) => c.kind === 'kept');
    expect(kept?.rawKey).toBe('domain_hint');
    expect(kept?.label).toBe('topic');
  });

  it('returns an empty list when the record has no after payload', () => {
    expect(memoryChips(record({ raw: null }))).toEqual([]);
    expect(memoryChips(undefined)).toEqual([]);
  });

  it('does not treat an empty array as a set value', () => {
    const chips = memoryChips(record({ raw: { before: {}, after: { entities: [] } } }));
    expect(chips).toEqual([]);
  });
});

describe('canRetry (AC-253/AC-257 client-side guard)', () => {
  it('is true only when status is failed', () => {
    expect(canRetry(turn({ status: 'failed' }))).toBe(true);
    expect(canRetry(turn({ status: 'done' }))).toBe(false);
    expect(canRetry(turn({ status: 'delegated' }))).toBe(false);
  });
});

describe('formatMs / turnDuration / shortTurnId', () => {
  it('formats sub-second durations in ms and larger ones in seconds', () => {
    expect(formatMs(420)).toBe('420 ms');
    expect(formatMs(4200)).toBe('4.2 s');
  });

  it('computes total wall time from created_at/finished_at', () => {
    const t = turn({ created_at: '2026-09-05T06:00:00.000Z', finished_at: '2026-09-05T06:00:04.100Z' });
    expect(turnDuration(t)).toBe('4.1 s');
  });

  it('is null while the turn has not finished', () => {
    expect(turnDuration(turn({ finished_at: null }))).toBeNull();
  });

  it('never surfaces a bare UUID (cursor rule)', () => {
    const id = '8f2c41d6-0b7a-4d33-9c2e-11ab5f0e7a10';
    const short = shortTurnId(id);
    expect(short).not.toContain('-');
    expect(short.length).toBe(4);
  });
});
