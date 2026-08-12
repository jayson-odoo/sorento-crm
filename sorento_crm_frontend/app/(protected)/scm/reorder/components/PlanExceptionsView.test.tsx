/**
 * SCM S5 - PlanExceptionsView (UAC Group D).
 *
 * What these pin is the small set of claims the screen makes that a plainer list would
 * quietly drop:
 *
 *   - **The reduction is stated** (AC-D2b). Six exceptions out of 412 changed lines is the
 *     filter working; showing only the six reads as a thin result.
 *   - **The actions arrive ordered by the item's READING, not by quantity** (AC-D10), and
 *     the grid never re-sorts them. Three rows with identical arithmetic propose three
 *     different first actions, and a discontinued surplus proposes keeping the order
 *     (AC-D11) rather than cancelling it.
 *   - **The staleness note is on the screen**, because nothing here reacts to a project
 *     moving until the order book is re-uploaded.
 *   - **Open is the default filter**: the queue is what is left to decide.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

const mockUsePlanExceptions = vi.fn();
const mockMutate = vi.fn();

vi.mock('../hooks/usePlanExceptions', () => ({
  usePlanExceptions: (...args: unknown[]) => mockUsePlanExceptions(...args),
  useDecidePlanException: () => ({ mutate: mockMutate, isPending: false }),
  planExceptionsKey: () => ['scm', 'reorder', 'plan-exceptions', null, null],
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Same reason as the worklist test: the grid renders no rows until the listing
// personalization hook is mocked, because it fetches through react-query.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

import { PlanExceptionsView } from './PlanExceptionsView';
import type {
  ItemReading,
  PlanException,
  PlanExceptionReport,
  ProposedAction,
} from '../types/planException.types';

function reading(lifecycle: string, velocity: string, business: string): ItemReading {
  return {
    lifecycle: { value: lifecycle, source: 'products.is_discontinued' },
    velocity: { value: velocity, source: 'scm.item_classification' },
    business: { value: business, source: 'market_segments.demand_class' },
    last_po: { value: '2026-03-02', source: 'purchase_orders.order_date' },
  };
}

function action(code: ProposedAction['code'], rank: number): ProposedAction {
  return {
    code,
    rank,
    rationale: `rank ${rank}`,
    candidate_so_number: null,
    candidate_need_by: null,
    candidate_warehouse_code: null,
  };
}

function exc(over: Partial<PlanException> = {}): PlanException {
  return {
    exception_id: 'exc-1',
    exception_type: 'supply_surplus',
    product_code: 'SRT367-GM',
    product_name: 'Sorento 367 Gunmetal',
    uom: 'PCS',
    warehouse_code: 'MWH-S/L',
    pool_code: 'MWH-S/L',
    po_number: 'PO26-0411',
    po_expected_date: '2026-09-18',
    quantity: 240,
    timeline: {
      before_points: [{ date: '2026-08-04', net: 60, label: null }],
      after_points: [{ date: '2026-08-04', net: 60, label: null }],
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: reading('Discontinued', 'C / Z', 'Retail'),
    actions: [action('keep_and_pool', 1), action('relink_so', 2)],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
    ...over,
  };
}

function report(over: Partial<PlanExceptionReport> = {}): PlanExceptionReport {
  const rows = over.rows ?? [exc()];
  return {
    run_id: 'run-1',
    as_of: '2026-08-04',
    generated_at: '2026-08-04T17:58:00',
    last_upload_at: '2026-08-04T17:55:00',
    counts: {
      delta_count: 412,
      exception_count: rows.length,
      open_count: rows.filter((r) => r.status === 'open').length,
      approved_count: rows.filter((r) => r.status === 'approved').length,
      rejected_count: rows.filter((r) => r.status === 'rejected').length,
    },
    ...over,
    rows,
  };
}

function ok(data: PlanExceptionReport) {
  mockUsePlanExceptions.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  mockUsePlanExceptions.mockReset();
  mockMutate.mockReset();
});

describe('PlanExceptionsView', () => {
  it('states the reduction from changed lines to exceptions', () => {
    ok(report());
    render(<PlanExceptionsView />);
    // Both figures, because the reduction is the value of the screen (AC-D2b).
    expect(
      screen.getByText(/1 of 412 changed lines disagree with supply already placed/),
    ).toBeInTheDocument();
  });

  it('says how current it is, because nothing reacts until the book is re-uploaded', () => {
    ok(report());
    render(<PlanExceptionsView />);
    expect(screen.getByText(/Current as of the last order-book upload/)).toBeInTheDocument();
    expect(screen.getByText(/A change nobody has uploaded is not here yet/)).toBeInTheDocument();
  });

  it('proposes a DIFFERENT first action for identical arithmetic on differently-read items', () => {
    // The inversion (AC-D10/AC-D11). Same type, same quantity; only the reading differs.
    ok(
      report({
        rows: [
          exc({
            exception_id: 'a',
            product_code: 'SRT367-GM',
            reading: reading('Discontinued', 'C / Z', 'Retail'),
            actions: [action('keep_and_pool', 1), action('relink_so', 2)],
          }),
          exc({
            exception_id: 'b',
            product_code: 'C-FH24',
            reading: reading('Active', 'A / X', 'Project'),
            actions: [action('relink_so', 1), action('split', 2)],
          }),
          exc({
            exception_id: 'c',
            product_code: 'ACC6002',
            reading: reading('Active', 'C / Z', 'Retail'),
            actions: [action('push_eta', 1), action('accept', 2)],
          }),
        ],
      }),
    );
    render(<PlanExceptionsView />);

    const discontinued = screen.getByRole('row', { name: /SRT367-GM/ });
    expect(within(discontinued).getByText('Keep the order and pool the stock')).toBeInTheDocument();
    // Never proposed FIRST for a discontinued item: it is the last stock obtainable.
    expect(within(discontinued).queryByText('Push the arrival date out')).toBeNull();

    expect(
      within(screen.getByRole('row', { name: /C-FH24/ })).getByText('Move to another order'),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('row', { name: /ACC6002/ })).getByText('Push the arrival date out'),
    ).toBeInTheDocument();
  });

  it('shows the reading beside the row so the ordering is arguable', () => {
    ok(report());
    render(<PlanExceptionsView />);
    expect(screen.getByText('Discontinued · C / Z · Retail')).toBeInTheDocument();
  });

  it('defaults to the open queue and hides decided rows', () => {
    ok(
      report({
        rows: [
          exc({ exception_id: 'open-1', product_code: 'SRT367-GM' }),
          exc({
            exception_id: 'done-1',
            product_code: 'SRTWC8613-RL',
            status: 'approved',
            decided_by: 'Joey Tan',
            decided_at: '2026-08-04T18:12:00',
            decided_action: 'push_eta',
          }),
        ],
      }),
    );
    render(<PlanExceptionsView />);
    expect(screen.getByRole('row', { name: /SRT367-GM/ })).toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /SRTWC8613-RL/ })).toBeNull();
  });

  it('says nothing disagrees rather than showing an empty grid', () => {
    ok(report({ rows: [] }));
    render(<PlanExceptionsView />);
    expect(screen.getByText('Nothing disagrees with placed supply.')).toBeInTheDocument();
  });

  it('states that approving writes an allocation decision, not a PO amendment', () => {
    ok(report());
    render(<PlanExceptionsView />);
    // AC-D7 on the screen: no placed PO is amended by a decision here.
    expect(
      screen.getByText(/No purchase order is amended without it/),
    ).toBeInTheDocument();
  });

  it('renders the error state with a retry rather than an empty list', () => {
    mockUsePlanExceptions.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('backend exploded'),
      refetch: vi.fn(),
    });
    render(<PlanExceptionsView />);
    expect(screen.getByText('Plan exceptions could not be loaded.')).toBeInTheDocument();
    expect(screen.getByText('backend exploded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('renders a loading skeleton while the batch is being read', () => {
    mockUsePlanExceptions.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    render(<PlanExceptionsView />);
    expect(screen.getByTestId('plan-exceptions-loading')).toBeInTheDocument();
  });
});

describe('PlanExceptionsView - onBack (this report has no row in the buy grid to return to)', () => {
  // The tile that used to open this view also carried the way back to the plan; once
  // it is gone, the screen needs its own exit.

  it('renders no back link when the caller supplies none', () => {
    ok(report());
    render(<PlanExceptionsView />);
    expect(screen.queryByText('Back to plan')).not.toBeInTheDocument();
  });

  it('calls onBack when "Back to plan" is clicked, with data on screen', () => {
    ok(report());
    const onBack = vi.fn();
    render(<PlanExceptionsView onBack={onBack} />);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the error state', () => {
    mockUsePlanExceptions.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('backend exploded'),
      refetch: vi.fn(),
    });
    const onBack = vi.fn();
    render(<PlanExceptionsView onBack={onBack} />);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the empty state', () => {
    ok(report({ rows: [] }));
    const onBack = vi.fn();
    render(<PlanExceptionsView onBack={onBack} />);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });
});
