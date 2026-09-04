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
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const getPlanningBoard = vi.fn();
const confirmSupply = vi.fn();
const confirmMany = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: vi.fn(),
  getSupply: vi.fn(),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  confirmMany: (...args: unknown[]) => confirmMany(...args),
  // S4 (`useLineDraftMutation`): `decide()` closes over these regardless of whether a test
  // presses Save deep enough to reach them.
  putLineDraft: vi.fn().mockResolvedValue({
    decision: { verdict: 'approved' },
    saved_by: 'Test Planner',
    saved_at: '2026-09-03T00:00:00Z',
  }),
  deleteLineDraft: vi.fn().mockResolvedValue(undefined),
  ConfirmSupplyError: class ConfirmSupplyError extends Error {
    readonly failingLines: unknown[] = [];
  },
}));

const getPlanningChangeBatch = vi.fn();

vi.mock('../../_shared/services/planningChangeService', () => ({
  listPlanningChangeBatches: vi.fn(),
  getPlanningChangeBatch: (...args: unknown[]) =>
    getPlanningChangeBatch(...args),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

// S4: `decide()` names the saver off the session (R-F).
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'user-1', name: 'Test Planner' } },
    status: 'authenticated',
  }),
}));

/**
 * `BoardTransfersPanel` (D4) is on this screen now, above the matrix. Its own behaviour is
 * `BoardTransfersPanel.test.tsx`'s; this mock only keeps the board itself renderable.
 */
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));
vi.mock('../../_shared/hooks/useBoardTransfers', () => ({
  // The real key, because the confirm hook invalidates it by name (D6).
  BOARD_TRANSFERS_KEY: 'board-stock-transfers',
  useBoardTransfers: () => ({
    data: { data: [] },
    isLoading: false,
    error: undefined,
  }),
  useBoardTransferMutations: () => ({
    approve: { mutate: vi.fn(), isPending: false },
    approveAll: { mutate: vi.fn(), isPending: false },
  }),
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
    <select
      aria-label={id ?? 'granularity'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import {
  buildBoard,
  type BoardDemandLine,
} from '../../_shared/lib/__testsupport__/boardFixture';
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
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel
        soNumbers={soNumbers}
        batchId={batchId}
        onBack={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getPlanningBoard.mockResolvedValue(
    buildBoard([demand()], {
      today: TODAY,
      freeStock: {},
      granularity: 'week',
    }),
  );
  getPlanningChangeBatch.mockResolvedValue(
    MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
  );
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
    expect(within(advanced).getByTestId('change-now-qty')).toHaveTextContent(
      '25',
    );

    // A closed line has left the board, so it is annotated on the surviving cell of the same
    // product on the same order rather than disappearing with its own cell.
    expect(screen.getByTestId('board-change-pcr-381895-2')).toBeInTheDocument();
    expect(screen.getByTestId('board-change-pcr-381895-3')).toBeInTheDocument();
  });

  it('reads Closed in the Now column of a line the book closed', async () => {
    renderPanel();
    const closed = await screen.findByTestId('board-change-pcr-381895-2');
    expect(within(closed).getByTestId('change-now-qty')).toHaveTextContent(
      'Closed',
    );
    expect(within(closed).getByTestId('change-now-decision')).toHaveTextContent(
      'Closed',
    );
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

/**
 * R13/D1/D5 retired the per-order commit rail this describe block was written against: no
 * `commit-row-*` card, no `commit-blocked` per order, no "Confirm this order" button. The
 * board's ONE Confirm posts through `confirmMany`, and AC-P3-4 still holds: when the board was
 * opened on a planning-change batch, the body names it (`batch_id`) so the apply and the
 * confirmation stay one atomic write on the server.
 */
describe('the pre-marked decision, and Confirm', () => {
  it('arrives with the changed line already decided', async () => {
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');
    fireEvent.click(
      await screen.findByRole('button', {
        name: /SRTWCX7405-RL-S-PJ, .* across 1 sales order/,
      }),
    );

    // The cell dialog opens on its Stock tab, so the pill lives one press away. Radix's
    // TabsTrigger switches on MOUSE DOWN; a bare `click` leaves the old panel up.
    const linesTab = await screen.findByRole('tab', {
      name: /^Contributing lines/,
    });
    fireEvent.mouseDown(linesTab);
    fireEvent.click(linesTab);

    // Saved (S4, R-F), not Approved: the pre-marked verdict is a decision like any other.
    await waitFor(() => {
      expect(
        screen.getByTestId(
          'decision-pill-so-381895|1|SRTWCX7405-RL-S-PJ|2026-08-17',
        ),
      ).toHaveTextContent('Saved');
    });
  });

  it('posts through confirmMany once Confirm is pressed, carrying the pre-marked line', async () => {
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-381895',
          ok: true,
          decision_revision: 3,
          inquiry_rows_created: 1,
        },
      ],
    });
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm')).toHaveTextContent(
        'Confirm (1)',
      ),
    );

    fireEvent.click(screen.getByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    expect(body.orders).toHaveLength(1);
    // The board fixture's own `pso-${sales_order_id}` (`ordersFor`), not the mock batch's
    // (unrelated) `pso-381895` - the confirm body is addressed off the BOARD, never the batch.
    expect(body.orders[0].pso_id).toBe('pso-so-381895');
    expect(body.orders[0].lines).toHaveLength(1);
    // AC-P3-4: the batch the board was opened on rides on the confirm body.
    expect(body.batch_id).toBe('pcb-so381895');
  });

  /**
   * One press confirms every plannable order on the board now (R11) - there is no per-order
   * card left to block selectively. So a batch NOT yet applied blocks nothing, even though one
   * order's own rows already read `applied_state: 'applied'`: the board-wide block reads only
   * `changeBatch.data.applied_at`.
   */
  it('does not block Confirm while the batch itself has not been applied, even if a row says it was', async () => {
    getPlanningChangeBatch.mockResolvedValue({
      ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
      applied_at: null,
      applied_by_name: null,
      orders: MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.orders.map((order) => ({
        ...order,
        rows: order.rows.map((row) => ({
          ...row,
          applied_state: 'applied' as const,
        })),
      })),
    });
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');

    expect(screen.queryByTestId('confirm-blocked')).not.toBeInTheDocument();
    expect(screen.getByTestId('board-confirm')).toBeEnabled();
  });

  it('refuses Confirm once the batch itself was applied, and says when and by whom', async () => {
    getPlanningChangeBatch.mockResolvedValue({
      ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
      applied_at: '2026-08-19T10:00:00Z',
      applied_by_name: 'Cyndi Tee',
    });
    renderPanel();
    await screen.findByTestId('board-change-pcr-381895-1');

    const blocked = await screen.findByTestId('confirm-blocked');
    expect(blocked).toHaveTextContent('This planning change was applied');
    expect(blocked).toHaveTextContent('Cyndi Tee');
    expect(screen.getByTestId('board-confirm')).toBeDisabled();
  });
});
