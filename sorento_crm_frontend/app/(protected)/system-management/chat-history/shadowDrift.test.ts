/**
 * Shadow-vs-live drift (AC-1029, AC-1030). Covers `driftAxes`, `rowDrift` and
 * `shadowSummaryLine` - the three pure rules the drift badge, the drawer's Parser
 * drift row and the list header line all read.
 */
import { describe, it, expect } from 'vitest';
import { driftAxes, rowDrift, shadowSummaryLine } from './shadowDrift';
import type { ChatbotTurn, ShadowTurnLiveSide } from './types/chatbotTurn.types';

const live = (over: Partial<ShadowTurnLiveSide> = {}): ShadowTurnLiveSide =>
  ({ id: 'live-1', branch_kind: 'business_query', domains: ['inventory'], ...over }) as ShadowTurnLiveSide;

const shadow = (over: Partial<ChatbotTurn> = {}): ChatbotTurn =>
  ({
    branch_kind: 'business_query',
    domains: ['inventory'],
    shadow_of: 'live-1',
    live: null,
    ...over,
  }) as unknown as ChatbotTurn;

describe('driftAxes', () => {
  it('agrees when branch and domains match: no drift', () => {
    expect(driftAxes(live(), shadow())).toEqual([]);
  });

  it('an unknown (null) side is not counted as drift, on either axis', () => {
    // branch_kind null on the live side (failed before routing)
    expect(driftAxes(live({ branch_kind: null }), shadow())).toEqual([]);
    // domains null on the shadow side (parsed under a pre-v3 label)
    expect(driftAxes(live(), shadow({ domains: null }))).toEqual([]);
  });

  it('no live row at all is not drift - there is nothing to compare against', () => {
    expect(driftAxes(null, shadow())).toEqual([]);
    expect(driftAxes(undefined, shadow())).toEqual([]);
  });

  it('a different branch_kind is branch-only drift', () => {
    expect(driftAxes(live({ branch_kind: 'out_of_scope' }), shadow())).toEqual(['branch']);
  });

  it('the same two domains in a different ORDER still count as drift', () => {
    // D11: sections render in the order the dealer named the domains, so "order,
    // incoming" and "incoming, order" are different answers even with the same set.
    expect(
      driftAxes(
        live({ domains: ['inventory', 'incoming'] }),
        shadow({ domains: ['incoming', 'inventory'] }),
      ),
    ).toEqual(['domains']);
  });

  it('a different domain list is domains-only drift', () => {
    expect(driftAxes(live({ domains: ['inventory'] }), shadow({ domains: ['order'] }))).toEqual([
      'domains',
    ]);
  });

  it('both axes disagreeing report both, branch first (fixed order)', () => {
    expect(
      driftAxes(
        live({ branch_kind: 'out_of_scope', domains: ['inventory'] }),
        shadow({ branch_kind: 'business_query', domains: ['order'] }),
      ),
    ).toEqual(['branch', 'domains']);
  });
});

describe('rowDrift', () => {
  it('reads the live side off the shadow row itself, for a cross-contact grid', () => {
    const row = shadow({ live: live({ branch_kind: 'out_of_scope' }) });
    expect(rowDrift(row)).toEqual(['branch']);
  });

  it('no live side on the row at all is not drift', () => {
    expect(rowDrift(shadow({ live: null }))).toEqual([]);
  });
});

describe('shadowSummaryLine', () => {
  it('is null when there is nothing to summarise', () => {
    expect(shadowSummaryLine(null)).toBeNull();
    expect(shadowSummaryLine(undefined)).toBeNull();
  });

  it('is null when the count is zero, even if parities are somehow present', () => {
    expect(shadowSummaryLine({ count: 0, branch_parity: 1, asks_parity: 1 })).toBeNull();
  });

  it('renders count and both percentages when they can be measured', () => {
    const line = shadowSummaryLine({ count: 12, branch_parity: 0.75, asks_parity: 0.5 });
    expect(line).toContain('12 shadow turns');
    expect(line).toContain('branch parity 75%');
    expect(line).toContain('asks parity 50%');
  });

  it('singular "turn" for a count of one', () => {
    expect(shadowSummaryLine({ count: 1, branch_parity: 1, asks_parity: 1 })).toContain(
      '1 shadow turn',
    );
    expect(shadowSummaryLine({ count: 1, branch_parity: 1, asks_parity: 1 })).not.toContain(
      '1 shadow turns',
    );
  });

  it('says "not measured" rather than 0% when a parity cannot be computed', () => {
    const line = shadowSummaryLine({ count: 3, branch_parity: null, asks_parity: null });
    expect(line).toContain('branch parity not measured');
    expect(line).toContain('asks parity not measured');
    expect(line).not.toContain('0%');
  });
});
