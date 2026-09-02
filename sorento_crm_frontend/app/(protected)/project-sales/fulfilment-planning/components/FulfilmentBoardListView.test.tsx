/**
 * The board as a LIST (D2, PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so
 * Approve all can be seen from an overview"): one row per contributing line, across every cell
 * of the board, with the same `onDecide` write path the grid view uses.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

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
    onDecide?: (key: string, decision: BoardDecision | null) => void;
    isLoading?: boolean;
  } = {},
) {
  const onDecide = overrides.onDecide ?? vi.fn();
  const utils = render(
    <FulfilmentBoardListView
      contributions={overrides.contributions ?? [contribution()]}
      draft={overrides.draft ?? {}}
      onDecide={onDecide}
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

  /** No revision number on the pill (R6): "Confirmed", full stop. */
  it('shows a pill reading Confirmed for a row already covered by an active decision, with no rev', async () => {
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

    const pill = await screen.findByTestId('decision-pill-so-1:line-10');
    expect(pill.textContent).toBe('Confirmed');
  });

  it('calls onDecide with an approved verdict from the expanded row’s Save (pill + panel, not a row button)', async () => {
    const { onDecide } = renderView();

    // No row-level Approve button any more: the row expands into the same panel the grid
    // uses, and its one Save reads the untouched suggestion as an approval.
    // Clicked on the Agent cell, not the Sales order cell - that one is a `Link` that stops
    // the click from bubbling to the row, on purpose (it navigates instead of expanding).
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    await screen.findByText('SO397450');
    fireEvent.click(screen.getByText('JEREMY'));
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    await waitFor(() =>
      expect(onDecide).toHaveBeenCalledWith('so-1:line-10', {
        verdict: 'approved',
        suspected_system_issue: false,
      }),
    );
  });

  it('updates the pill when the draft prop carries a decision for the row', async () => {
    const row = contribution();
    const { rerender } = render(
      <FulfilmentBoardListView contributions={[row]} draft={{}} onDecide={vi.fn()} />,
    );

    expect(
      await screen.findByTestId('decision-pill-so-1:line-10'),
    ).toHaveTextContent('Suggested');

    rerender(
      <FulfilmentBoardListView
        contributions={[row]}
        draft={{ [row.key]: { verdict: 'approved' } }}
        onDecide={vi.fn()}
      />,
    );

    // Saved (S4, R-F), not Approved - the pill reads the plain "has this been dealt with"
    // word once a decision exists, whichever of the two verbs produced it.
    expect(
      await screen.findByTestId('decision-pill-so-1:line-10'),
    ).toHaveTextContent('Saved');
  });

  it('quotes THIS line\u2019s own Available beside the Reserve input (C4)', async () => {
    renderView({
      contributions: [
        contribution({
          fulfilment_location: 'BRW-AM',
          fulfilment_warehouse_id: 'wh-am',
          sources: [
            {
              kind: 'reserve',
              qty: '9',
              location: 'BRW-AM',
              warehouse_id: 'wh-am',
              reason: 'Own group.',
            },
            { kind: 'buy', qty: '34', reason: 'The rest is bought.' },
          ],
          // The figures ride on the contribution, netted of this line's own quantity: the
          // list spans every cell, so there is no cell to read them off.
          locations: [
            {
              location: 'BRW-AM',
              warehouse_id: 'wh-am',
              product_id: 'prod-1',
              qty: '43',
              qty_demand: '43',
              available_qty: '9',
              qty_free: '9',
              qty_free_remaining: '9',
            },
          ],
        }),
      ],
    });

    await screen.findByText('SO397450');
    fireEvent.click(screen.getByText('JEREMY'));

    expect(await screen.findByText('9 available')).toBeInTheDocument();
  });

  it('asks before it closes a row holding an unsaved edit (C5)', async () => {
    renderView({
      contributions: [
        contribution(),
        contribution({ key: 'so-1:line-20', line_no: 20, so_number: 'SO397451' }),
      ],
    });

    await screen.findByText('SO397450');
    fireEvent.click(screen.getAllByText('JEREMY')[0]);
    // An edit nobody has saved: the reason box on the open panel.
    fireEvent.change(screen.getByPlaceholderText('In your own words'), {
      target: { value: 'The group is short' },
    });

    fireEvent.click(screen.getAllByText('JEREMY')[1]);

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'Leave this decision unsaved?',
    );
    // Kept open until the question is answered.
    expect(screen.getByText('The group is short')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    );
  });

  it('marks an unplannable line rather than offering it a verdict', async () => {
    renderView({ contributions: [contribution({ unplannable: true })] });

    // Both the Suggested and the Verdict cells read "Needs a location" for an unplannable
    // line - the ladder was never walked, so there is nothing else either could say.
    expect(await screen.findAllByText('Needs a location')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });
});

describe('FulfilmentBoardListView marks a row whose supply is already decided', () => {
  /**
   * The same tick the grid puts on a fully-decided cell, here per row - one row IS one
   * contribution, so it is decided or it is not. The Verdict column already states the
   * revision in words; this is what makes it scannable down a list of two hundred.
   */
  const decided = (revisionNo: number) =>
    contribution({
      covered: true,
      decision: {
        revision_no: revisionNo,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '43',
      },
    });

  it('ticks the row and names the revision', async () => {
    renderView({ contributions: [decided(3)] });

    const marker = await screen.findByTestId('board-decided-marker');
    expect(marker).toHaveAttribute('title', 'Decided rev 3');
  });

  it('leaves an undecided row unticked', async () => {
    renderView();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.queryByTestId('board-decided-marker')).not.toBeInTheDocument();
  });
});

/**
 * The list draws the SAME bar the grid does, off the same draft (PLAN section C).
 *
 * Two readings of one board that disagreed about a colour would be worse than one reading: the
 * planner would have to work out which of them was lying.
 */
describe('FulfilmentBoardListView agrees with the grid about the supply bar', () => {
  it('draws the proposal faded on an undecided row', async () => {
    renderView({
      contributions: [
        contribution({
          sources: [
            { kind: 'reserve', rung: 'pool', qty: '43', location: 'BRW', reason: 'pool' },
          ],
        }),
      ],
    });

    const bar = await screen.findByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    expect(bar.querySelector('span[data-kind="shared"]')).not.toBeNull();
  });

  it('draws the DECISION, solid, once the row is ticked in the draft', async () => {
    renderView({
      contributions: [
        contribution({
          sources: [
            { kind: 'buy', rung: 'buy', qty: '43', reason: 'Nothing free at any location.' },
            {
              kind: 'reserve',
              rung: 'pool',
              qty: '0',
              location: 'BRW',
              warehouse_id: 'wh-brw',
              reason: 'pool',
            },
          ],
        }),
      ],
      draft: {
        'so-1:line-10': {
          verdict: 'amended',
          reserve: [{ warehouse_id: 'wh-brw', location: 'BRW', qty: '43' }],
          borrow: [],
          buy_qty: '0',
          reason: 'The pool can cover it',
        },
      },
    });

    // Two bars per row since AC-D4 split the column in two: Suggested first, Decided
    // second. It is the DECIDED one that has to go solid.
    const bars = await screen.findAllByTestId('supply-bar');
    expect(bars).toHaveLength(2);
    expect(bars[0]).toHaveAttribute('data-decided', 'false');
    const bar = bars[1];
    expect(bar).toHaveAttribute('data-decided', 'true');
    expect(bar.querySelector('span[data-kind="shared"]')).not.toBeNull();
    expect(bar.querySelector('span[data-kind="buy"]')).toBeNull();
  });
});

/**
 * AC-D4: Suggested and Decided, side by side, in PLAN section 2's own words.
 *
 * One "Proposal" column used to show the DECISION on a decided line and the PROPOSAL on an
 * undecided one, so the one comparison the planner opens this view to make - did we do what
 * the engine said - could not be made at all.
 */
describe('FulfilmentBoardListView says what was suggested and what was decided', () => {
  const amended = contribution({
    covered: true,
    fulfilment_location: 'BRW-BB',
    proposed: {
      components: [
        { kind: 'reserve', rung: 'pool', qty: '43', location: 'BRW', reason: 'pool' },
      ],
    },
    sources: [{ kind: 'buy', rung: 'buy', qty: '43', reason: 'Bought, as confirmed.' }],
    decision: {
      revision_no: 1,
      timely_spo_qty: '0',
      reserve: [],
      borrow: [],
      buy_qty: '43',
    },
  });

  it('carries both columns', async () => {
    renderView({ contributions: [amended] });

    expect(await screen.findByText('Suggested')).toBeInTheDocument();
    expect(screen.getByText('Decided')).toBeInTheDocument();
  });

  it('states the engine composition on one side and the decision on the other', async () => {
    renderView({ contributions: [amended] });

    expect(await screen.findByText('BRW 43 (BRW)')).toBeInTheDocument();
    expect(screen.getByText('Buy 43')).toBeInTheDocument();
  });

  it('says Not recorded, never "nothing", for a revision that froze no proposal', async () => {
    const old = contribution({
      covered: true,
      sources: [{ kind: 'buy', rung: 'buy', qty: '43', reason: 'Bought, as confirmed.' }],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '43',
      },
    });

    renderView({ contributions: [old] });

    expect(await screen.findByText('Not recorded')).toBeInTheDocument();
  });

  it('says Not decided while nobody has decided the line', async () => {
    renderView({
      contributions: [
        contribution({
          proposed: {
            components: [
              { kind: 'reserve', rung: 'pool', qty: '43', location: 'BRW', reason: 'pool' },
            ],
          },
        }),
      ],
    });

    expect(await screen.findByText('Not decided')).toBeInTheDocument();
  });
});
