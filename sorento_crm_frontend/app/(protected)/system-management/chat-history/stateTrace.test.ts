/**
 * Client-side state-transition summary. Kept in lockstep with the SQL view
 * `public.v_turn_state_transition` (migration 295) — these cases mirror the
 * psql assertions in the state-transition-monitor CRM plan (UAC-CRM-2, -5).
 */
import { describe, it, expect } from 'vitest';
import { deriveStateSummary } from './stateTrace';
import type { StateTrace } from './types/chatHistory.types';

const ent = (raw: string, type?: string) => ({ raw, entity_type: type });

describe('deriveStateSummary', () => {
  it('gains an entity when it appears in after but not before (turn 1)', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [] },
      parser_applied: { domain_signal_source: 'current_message' },
      after: { entities: [ent('tan trading', 'customer')] },
    };
    const s = deriveStateSummary(t)!;
    expect(s.wroteState).toBe(true);
    expect(s.entitiesLost).toEqual([]);
    expect(s.entitiesGained).toEqual(['customer:tan trading']);
    expect(s.causeFlags).toEqual(['source=current_message']);
  });

  it('loses nothing on a dym merge-back turn (turn 2)', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [ent('tan trading', 'customer')] },
      parser_raw: { domain_hint: 'wrong', scope_exclusive: true },
      parser_applied: {
        domain_hint: 'products',
        scope_exclusive: false,
        dym_pick_applied: true,
        entity_op_applied: true,
        domain_signal_source: 'dym',
      },
      after: { entities: [ent('tan trading', 'customer'), ent('SRTWC286', 'product')] },
    };
    const s = deriveStateSummary(t)!;
    expect(s.entitiesLost).toEqual([]);
    expect(s.entitiesGained).toEqual(['product:SRTWC286']);
    expect(s.causeFlags).toEqual(['dym_pick_applied', 'entity_op_applied', 'source=dym']);
    // post-processing overruled the LLM's domain + scope
    expect(s.parserDrift).toEqual(['domain', 'scope']);
  });

  it('is the defect signature on turn 3: entity lost + scope_exclusive + NO dym', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [ent('tan trading', 'customer')] },
      parser_applied: {
        scope_exclusive_applied: true,
        entity_op_applied: true,
        domain_signal_source: 'current_message',
      },
      after: { entities: [ent('SRTWC287', 'product')] },
    };
    const s = deriveStateSummary(t)!;
    expect(s.entitiesLost).toEqual(['customer:tan trading']);
    expect(s.causeFlags).toContain('scope_exclusive_applied');
    expect(s.causeFlags).not.toContain('dym_pick_applied');
  });

  it('suppresses set arithmetic to null when the turn wrote no state (after: null)', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [ent('secret co', 'customer')] },
      parser_applied: {},
      after: null,
    };
    const s = deriveStateSummary(t)!;
    // NOT [] — absence of a write is not evidence of a loss.
    expect(s.wroteState).toBe(false);
    expect(s.entitiesLost).toBeNull();
    expect(s.entitiesGained).toBeNull();
  });

  it('treats a case/whitespace-only change as neither lost nor gained (N2 identity)', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [ent('Tan Trading', 'customer')] },
      parser_applied: {},
      after: { entities: [ent('  tan trading ', 'customer')] },
    };
    const s = deriveStateSummary(t)!;
    expect(s.entitiesLost).toEqual([]);
    expect(s.entitiesGained).toEqual([]);
  });

  it('reports parserDrift null when parser_raw was never captured', () => {
    const t: StateTrace = {
      v: 1,
      before: { entities: [] },
      parser_applied: { entities: [] },
      after: { entities: [] },
    };
    expect(deriveStateSummary(t)!.parserDrift).toBeNull();
  });

  it('returns null for an absent trace', () => {
    expect(deriveStateSummary(null)).toBeNull();
    expect(deriveStateSummary(undefined)).toBeNull();
  });
});
