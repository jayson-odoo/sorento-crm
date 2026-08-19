/**
 * The board as a LIST (D2, PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so
 * Approve all can be seen from an overview"): one row per contributing line, across every cell
 * of the board, with the same `onDecide` write path the grid view uses.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BoardContribution, BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { FulfilmentBoardListView } from './FulfilmentBoardListView';

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:line-10',
    sales_order_id: 'so-1',
    line_id: 'core-line-10',
    product_id: 'prod-1',
    so_number: 'SO397450',
    customer_name: 'Tuju Residences Sdn Bhd',
    agent_code: 'JEREMY',
    agent_label: 'Jeremy Lee',
    project_label: 'Tuju Residences',
    line_no: 10,
    item_code: 'B2155-NL-BLUE',
    qty: '43',
    qty_outstanding: '43',
    required_date: '2026-09-04',
    unplannable: false,
    rank_score: 0.82,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '43', reason: 'Nothing free at any location.' }],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function renderView(
  overrides: {
    contributions?: BoardContribution[];
    draft?: BoardDraft;
    onDecide?: (key: string, decision: unknown) => void;
    isLoading?: boolean;
  } = {},
) {
  const onDecide = overrides.onDecide ?? vi.fn();
  const utils = render(
    <FulfilmentBoardListView
      contributions={overrides.contributions ?? [contribution()]}
      draft={overrides.draft ?? {}}
      onDecide={onDecide as (key: string, decision: never) => void}
      isLoading={overrides.isLoading}
    />,
  );
  return { ...utils, onDecide };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FulfilmentBoardListView', () => {
  it('renders one row per contributing line with SO, agent, product and proposal', async () => {
    renderView();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('Line 10')).toBeInTheDocument();
    expect(screen.getByText('JEREMY')).toBeInTheDocument();
    expect(screen.getByText('Tuju Residences Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('B2155-NL-BLUE')).toBeInTheDocument();
    expect(screen.getByText('Buy 43')).toBeInTheDocument();
  });

  it('renders one row per line when several contribute', async () => {
    renderView({
      contributions: [
        contribution({ key: 'so-1:line-10', so_number: 'SO397450', line_no: 10 }),
        contribution({ key: 'so-2:line-20', so_number: 'SO397451', line_no: 20 }),
      ],
    });

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('SO397451')).toBeInTheDocument();
    expect(screen.getByText('Line 10')).toBeInTheDocument();
    expect(screen.getByText('Line 20')).toBeInTheDocument();
  });

  it('shows the verdict for a row already covered by an active decision', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: {
            revision_no: 3,
            timely_spo_qty: '0',
            reserve: [],
            borrow: [],
            buy_qty: '43',
          },
        }),
      ],
    });

    expect(await screen.findByText('Confirmed rev 3')).toBeInTheDocument();
  });

  it('calls onDecide with an approved verdict when Approve is pressed on an undecided row', async () => {
    const { onDecide } = renderView();

    const approve = await screen.findByRole('button', { name: /approve/i });
    approve.click();

    await waitFor(() =>
      expect(onDecide).toHaveBeenCalledWith('so-1:line-10', { verdict: 'approved' }),
    );
  });

  it('updates the verdict cell when the draft prop carries a decision for the row', async () => {
    const row = contribution();
    const { rerender } = render(
      <FulfilmentBoardListView contributions={[row]} draft={{}} onDecide={vi.fn()} />,
    );

    expect(await screen.findByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.queryByText('Approved')).not.toBeInTheDocument();

    rerender(
      <FulfilmentBoardListView
        contributions={[row]}
        draft={{ [row.key]: { verdict: 'approved' } }}
        onDecide={vi.fn()}
      />,
    );

    expect(await screen.findByText('Approved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it('marks an unplannable line rather than offering it a verdict', async () => {
    renderView({ contributions: [contribution({ unplannable: true })] });

    // Both the Proposal and the Verdict cells read "Needs a location" for an unplannable
    // line - the ladder was never walked, so there is nothing else either could say.
    expect(await screen.findAllByText('Needs a location')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });
});
