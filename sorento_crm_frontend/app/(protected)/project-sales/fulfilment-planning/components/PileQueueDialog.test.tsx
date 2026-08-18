/**
 * The whole queue at one pile.
 *
 * The captain, having been shown the top three beside the rung: "I need to know what is ahead of
 * me to have the visibility, and why they are ahead of me, meaning I need to know their rank
 * also."
 *
 * So the dialog is the queue in the order the stock is served, with the running total beside it,
 * the asking line marked, and each row's rank one press from its own factor table.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getPileQueue = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPileQueue: (...args: unknown[]) => getPileQueue(...args),
}));

import { PileQueueDialog } from './PileQueueDialog';
import type { PileQueue, PileQueueLine } from '../../_shared/types/fulfilmentPlanning.types';

function line(overrides: Partial<PileQueueLine> = {}): PileQueueLine {
  return {
    position: 1,
    line_id: 'core-1',
    sales_order_id: 'so-1',
    so_number: 'SO391698',
    line_no: 3,
    customer_name: 'OIB CONSTRUCTION SDN BHD',
    qty: '120',
    required_date: '2026-09-12',
    order_date: '2026-01-05',
    payment_terms_days: 30,
    demand_class: 'project',
    rank_score: 0.95,
    rank_factors: [
      { key: 'need_by_date', weight: 3, value: 1, present: true, raw: '2026-09-12' },
      { key: 'customer_credit', weight: 1, value: null, present: false, raw: null },
    ],
    leading_factor: 'need_by_date',
    cumulative_ahead_qty: '120',
    is_this_line: false,
    is_covered_excluded: false,
    ...overrides,
  };
}

/** Three ahead, this line, and one behind: the shape the reader is actually looking at. */
function queue(overrides: Partial<PileQueue> = {}): PileQueue {
  return {
    product_id: 'prod-1',
    item_code: 'B2155-NL-BLUE',
    description: 'BLUE NYLON LEAF 2155',
    warehouse_id: 'wh-1',
    location: 'BRW-BB',
    qty_free_opening: '478',
    this_line_position: 4,
    policy_name: 'Fair fulfilment priority (delivery date, document date, customer credit)',
    lines: [
      line(),
      line({
        position: 2,
        line_id: 'core-2',
        sales_order_id: 'so-2',
        so_number: 'SO396351',
        line_no: 1,
        customer_name: 'MASUKA BINA SDN BHD',
        qty: '200',
        rank_score: 0.9,
        cumulative_ahead_qty: '320',
      }),
      line({
        position: 3,
        line_id: 'core-3',
        sales_order_id: 'so-3',
        so_number: 'SO403765',
        line_no: 1,
        qty: '158',
        rank_score: 0.8,
        leading_factor: 'line_order',
        cumulative_ahead_qty: '478',
      }),
      line({
        position: 4,
        line_id: 'core-4',
        sales_order_id: 'so-3',
        so_number: 'SO403765',
        line_no: 2,
        qty: '21',
        rank_score: 0.8,
        leading_factor: null,
        cumulative_ahead_qty: '499',
        is_this_line: true,
      }),
      line({
        position: 5,
        line_id: 'core-5',
        sales_order_id: 'so-5',
        so_number: 'SO404100',
        line_no: 1,
        qty: '40',
        rank_score: 0.2,
        leading_factor: null,
        cumulative_ahead_qty: '539',
      }),
    ],
    ...overrides,
  };
}

function renderDialog(lineId: string | null = 'core-4') {
  const onClose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <PileQueueDialog
        productId="prod-1"
        warehouseId="wh-1"
        lineId={lineId}
        itemCode="B2155-NL-BLUE"
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PileQueueDialog', () => {
  it('asks by IDS and on behalf of the line, because both change the answer', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    await waitFor(() => expect(getPileQueue).toHaveBeenCalledWith('prod-1', 'wh-1', 'core-4'));
  });

  it('states the pile, what it held, and where this line stands, once at the top', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    await waitFor(() =>
      expect(screen.getByTestId('queue-header-line')).toHaveTextContent(
        'BRW-BB · 478 free at opening · this line is #4 of 5',
      ),
    );
  });

  it('marks the asking line and says which factor put each line above it', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    const mine = await screen.findByTestId('queue-this-line');
    expect(mine).toHaveTextContent('4 (this line)');
    // Words, never the policy's own key.
    expect(screen.getAllByText('Required date').length).toBeGreaterThan(0);
    expect(screen.queryByText('need_by_date')).toBeNull();
    // A tie decided by line order is not a factor, and must not read as one.
    expect(screen.getByText('same order')).toBeInTheDocument();
  });

  it('says a row behind the asking line is behind it, rather than ahead of it', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    expect(await screen.findByText('Behind this line')).toBeInTheDocument();
  });

  it('shows the running total, so the row where the pile runs out is visible', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    expect(await screen.findByText('478')).toBeInTheDocument();
    expect(screen.getByText('499')).toBeInTheDocument();
  });

  it('offers each row its own factor table, the same one a board row carries', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    fireEvent.click(await screen.findByTestId('rank-info-core-1'));
    const calculation = await screen.findByTestId('rank-calculation-core-1');
    expect(within(calculation).getByTestId('rank-factor-need_by_date')).toBeInTheDocument();
    // The rule these weights belong to, named where somebody is already asking about a rank.
    expect(within(calculation).getByTestId('rank-policy-core-1')).toHaveTextContent(
      'Ranked by Fair fulfilment priority (delivery date, document date, customer credit)',
    );
  });

  it('names the ranking rule above the table rather than in a banner nobody asked for', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    expect(
      await screen.findByText(
        'Ranked by Fair fulfilment priority (delivery date, document date, customer credit)',
      ),
    ).toBeInTheDocument();
  });

  it('says a covered line is not in this queue, once, as a fact about the queue', async () => {
    getPileQueue.mockResolvedValue(queue());

    renderDialog();

    expect(
      await screen.findByText(/Lines a confirmed decision already covers are not in this queue/),
    ).toBeInTheDocument();
  });

  it('shows a skeleton while the queue is being read', () => {
    getPileQueue.mockReturnValue(new Promise(() => {}));

    renderDialog();

    expect(screen.getByTestId('queue-loading')).toBeInTheDocument();
  });

  it('says what went wrong rather than showing an empty queue', async () => {
    getPileQueue.mockRejectedValue(new Error('Backend is down'));

    renderDialog();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
  });

  it('says nothing is queuing when nothing is, rather than rendering an empty grid', async () => {
    getPileQueue.mockResolvedValue(queue({ lines: [], this_line_position: null }));

    renderDialog();

    expect(await screen.findByText('Nothing is queuing for this stock')).toBeInTheDocument();
  });

  it('reads the queue on nobody’s behalf when no line asked', async () => {
    getPileQueue.mockResolvedValue(queue({ this_line_position: null }));

    renderDialog(null);

    await waitFor(() =>
      expect(screen.getByTestId('queue-header-line')).toHaveTextContent(
        'BRW-BB · 478 free at opening · 5 lines in the queue',
      ),
    );
  });
});
