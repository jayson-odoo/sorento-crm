/**
 * The board opened ON a planning-change batch (`PLAN-scm-cs-planning-uat.md` part 3).
 *
 * AC-P3-2 (the Was / Now table on the changed cell, `Closed` on a line the book closed),
 * AC-P3-3 (the cell arrives pre-marked, in board words only), AC-P3-4 (Confirm carries the
 * batch and a batch already applied refuses a second press), AC-P3-9 (the moved transfer is
 * stated on the cell).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getPlanningBoard = vi.fn();
const confirmSupply = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: vi.fn(),
  getSupply: vi.fn(),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  confirmMany: vi.fn(),
  ConfirmSupplyError: class ConfirmSupplyError extends Error {
    readonly failingLines: unknown[] = [];
  },
}));

const getPlanningChangeBatch = vi.fn();

vi.mock('../../_shared/services/planningChangeService', () => ({
  listPlanningChangeBatches: vi.fn(),
  getPlanningChangeBatch: (...args: unknown[]) => getPlanningChangeBatch(...args),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    id?: string;
  }) => (
    <select aria-label={id ?? 'granularity'} value={value} onChange={(e) => onChange(e.target.value)}>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import { MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE } from '../../_shared/__mocks__/planningChanges';

const TODAY = '2026-08-18';

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-381895',
    so_number: 'SO381895',
    customer_name: 'YOTU BUILDER',
    project_sales_order_id: 'pso-381895',
    project_line_id: 'pl-381895-1',
    line_no: 1,
    item_code: 'SRTWCX7405-RL-S-PJ',
    qty: '25',
    required_date: '2026-08-19',
    fulfilment_location: 'BRW-IB',
    priority: null,
    ...overrides,
  } as BoardDemandLine;
}

function renderPanel(
  batchId: string | null = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.id,
  soNumbers: string[] = ['SO381895'],
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} batchId={batchId} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getPlanningBoard.mockResolvedValue(
    buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
  );
  getPlanningChangeBatch.mockResolvedValue(MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE);
});

describe('the changed cell', () => {
  it('shows a Was / Now table for the changed line and for both closed ones', async () => {
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const advanced = await screen.findByTestId('board-change-pcr-381895-1');
    expect(within(advanced).getByText('Was')).toBeInTheDocument();
    expect(within(advanced).getByText('Now')).toBeInTheDocument();
    expect(within(advanced).getByText('Qty')).toBeInTheDocument();
    expect(within(advanced).getByText('Date')).toBeInTheDocument();
    expect(within(advanced).getByText('Decision')).toBeInTheDocument();
    expect(within(advanced).getByTestId('change-now-qty')).toHaveTextContent('25');

    // A closed line has left the board, so it is annotated on the surviving cell of the same
    // product on the same order rather than disappearing with its own cell.
    expect(screen.getByTestId('board-change-pcr-381895-2')).toBeInTheDocument();
    expect(screen.getByTestId('board-change-pcr-381895-3')).toBeInTheDocument();
  });

  it('reads Closed in the Now column of a line the book closed', async () => {
    renderPanel();
    const closed = await screen.findByTestId('board-change-pcr-381895-2');
    expect(within(closed).getByTestId('change-now-qty')).toHaveTextContent('Closed');
    expect(within(closed).getByTestId('change-now-decision')).toHaveTextContent('Closed');
  });

  it('says a transfer already moved for a cancelled line, and proposes no reversal', async () => {
    renderPanel();
    const moved = await screen.findByTestId('board-change-moved-pcr-381895-2');
    expect(moved).toHaveTextContent('10 moved BRW -> BRW-IB, line cancelled');
  });

  it('never prints the batch reaction vocabulary on screen', async () => {
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');
    const printed = document.body.textContent ?? '';
    for (const verb of ['Retire', 'Replan', 'Reduce', 'Release']) {
      expect(printed).not.toContain(verb);
    }
  });

  it('shows no table at all on a board opened without a batch', async () => {
    renderPanel(null);
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.queryByTestId('board-change-pcr-381895-1')).toBeNull();
    expect(getPlanningChangeBatch).not.toHaveBeenCalled();
  });
});

describe('the pre-marked decision, and Confirm', () => {
  it('arrives with the changed line already decided', async () => {
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');
    await waitFor(() => {
      expect(screen.getByText(/1 approved/)).toBeInTheDocument();
    });
  });

  it('carries the batch on Confirm, so one press applies it and writes one revision', async () => {
    confirmSupply.mockResolvedValue({
      revision_no: 3,
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');
    await waitFor(() => expect(screen.getByText(/1 approved/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Confirm this order|Confirm 1 line/ }));

    await waitFor(() => expect(confirmSupply).toHaveBeenCalledTimes(1));
    const [, body] = confirmSupply.mock.calls[0];
    expect(body.batch_id).toBe(MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.id);
    expect(body.lines.length).toBe(1);
  });

  it('blocks only the order the batch has already been applied to', async () => {
    // One press confirms ONE order (B1). While another order of the same upload is still
    // waiting, the batch itself is not applied - so a batch-wide block would put a wall in
    // front of a change nobody has decided yet.
    getPlanningChangeBatch.mockResolvedValue({
      ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
      applied_at: null,
      applied_by_name: null,
      orders: MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.orders.map((order) => ({
        ...order,
        rows: order.rows.map((row) => ({ ...row, applied_state: 'applied' as const })),
      })),
    });
    getPlanningBoard.mockResolvedValue(
      buildBoard(
        [
          demand(),
          demand({
            sales_order_id: 'so-999999',
            so_number: 'SO999999',
            project_line_id: 'pl-999999-1',
            item_code: 'SRTWC287A-RL',
          }),
        ],
        { today: TODAY, freeStock: {}, granularity: 'week' },
      ),
    );
    renderPanel(MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.id, ['SO381895', 'SO999999']);
    await screen.findByTestId('fulfilment-board-matrix');

    const changed = await screen.findByTestId('commit-row-SO381895');
    expect(within(changed).getByTestId('commit-blocked')).toHaveTextContent(
      'This planning change was already applied to this sales order.',
    );
    const other = screen.getByTestId('commit-row-SO999999');
    expect(within(other).queryByTestId('commit-blocked')).toBeNull();
  });

  it('refuses a second Confirm on a batch already applied, and says when it was', async () => {
    getPlanningChangeBatch.mockResolvedValue({
      ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
      applied_at: '2026-08-19T10:00:00Z',
      applied_by_name: 'Cyndi Tee',
    });
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');

    const blocked = await screen.findByTestId('commit-blocked');
    expect(blocked).toHaveTextContent('This planning change was applied');
    expect(blocked).toHaveTextContent('Cyndi Tee');
    expect(
      screen.getByRole('button', { name: /Confirm this order|Confirm 1 line/ }),
    ).toBeDisabled();
  });
});
