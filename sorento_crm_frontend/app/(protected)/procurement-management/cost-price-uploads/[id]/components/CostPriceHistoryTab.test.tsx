/**
 * CostPriceHistoryTab (#1288, Lane A) - J14 + AC-AU-04: History must say who mapped,
 * skipped and decided each line, and why a line was rejected. The backend now writes
 * COST_LINE_MAP / COST_LINE_SKIP / COST_LINE_DECISION rows on the set; this test holds
 * the History tab to rendering every one of them with a human label, never the raw
 * action code, and to showing the reject reason carried in the summary.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.test.tsx`.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

type HistoryEvent = { action: string; at: string; summary: string; actor_name: string };

let events: HistoryEvent[] = [];
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeSetHistory: () => ({ data: { data: events }, isLoading: false }),
}));

import { CostPriceHistoryTab } from './CostPriceHistoryTab';

const AT = '2026-09-27T01:00:00Z';

describe('CostPriceHistoryTab line-level events', () => {
  it('labels every line-level action in words and never shows an action code', () => {
    events = [
      { action: 'COST_LINE_DECISION', at: AT, summary: 'ZZT-002: rejected - price looks wrong', actor_name: 'Kelvin' },
      { action: 'COST_LINE_DECISION', at: AT, summary: 'ZZT-001: accepted', actor_name: 'Kelvin' },
      { action: 'COST_LINE_SKIP', at: AT, summary: 'ZZT-003 skipped: discontinued', actor_name: 'Mei' },
      { action: 'COST_LINE_MAP', at: AT, summary: 'ZZT-004 mapped to P-100', actor_name: 'Mei' },
    ];
    render(<CostPriceHistoryTab setId="set-1" />);

    expect(screen.getAllByText('Decided a line')).toHaveLength(2);
    expect(screen.getByText('Skipped a line')).toBeInTheDocument();
    expect(screen.getByText('Mapped a line')).toBeInTheDocument();
    expect(screen.queryByText(/COST_[A-Z_]+/)).toBeNull();
  });

  it('shows the reject reason and who decided', () => {
    events = [
      { action: 'COST_LINE_DECISION', at: AT, summary: 'ZZT-002: rejected - price looks wrong', actor_name: 'Kelvin' },
    ];
    render(<CostPriceHistoryTab setId="set-1" />);

    expect(screen.getByText(/price looks wrong/)).toBeInTheDocument();
    expect(screen.getByText('Kelvin')).toBeInTheDocument();
  });

  it('falls back to a readable label for an action it does not know', () => {
    events = [{ action: 'COST_SET_SOMETHING_NEW', at: AT, summary: 'x', actor_name: 'Mei' }];
    render(<CostPriceHistoryTab setId="set-1" />);

    expect(screen.queryByText('COST_SET_SOMETHING_NEW')).toBeNull();
  });
});
