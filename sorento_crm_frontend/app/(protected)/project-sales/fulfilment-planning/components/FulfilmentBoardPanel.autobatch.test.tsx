/**
 * The board picks up a pending planning-change batch on its own
 * (`PLAN-scm-board-picks-up-pending-change.md`, AC-B2, AC-B3, AC-B4, AC-B6).
 *
 * Mirrors `FulfilmentBoardPanel.change.test.tsx`'s scaffolding (same mocks, same
 * `renderPanel` shape, same `demand()` fixture for SO381895) rather than copying its
 * assertions: that file pins the batch-from-URL contract, this one pins the batch-from-
 * the-board-response contract the plan adds beside it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  getPlanningChangeBatch: (...args: unknown[]) => getPlanningChangeBatch(...args),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'user-1', name: 'Test Planner' } },
    status: 'authenticated',
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));
vi.mock('../../_shared/hooks/useBoardTransfers', () => ({
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
import {
  MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
  MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE_2,
} from '../../_shared/__mocks__/planningChanges';

const TODAY = '2026-08-18';
const BATCH_A = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE; // SO381895, pso-381895
const BATCH_B = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE_2; // SO381896, pso-381896

function demandA(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
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

function demandB(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-381896',
    so_number: 'SO381896',
    customer_name: 'BATHE CODE SDN BHD',
    project_sales_order_id: 'pso-381896',
    project_line_id: 'pl-381896-1',
    line_no: 1,
    item_code: 'CB231SS-NL',
    qty: '15',
    required_date: '2026-09-03',
    fulfilment_location: 'BRW-BB',
    priority: null,
    ...overrides,
  } as BoardDemandLine;
}

/**
 * Stands in for the plan's own change: `BoardOrderStanding.pending_change_batch_id`, keyed
 * on `sales_order_id`. Not yet a field the real board response carries (nor the test-only
 * `buildBoard` fixture) - which is the whole point of these tests being red.
 */
function withPendingBatch(
  board: ReturnType<typeof buildBoard>,
  mapping: Record<string, string | null>,
): ReturnType<typeof buildBoard> {
  return {
    ...board,
    orders: board.orders.map((order) => ({
      ...order,
      pending_change_batch_id: mapping[order.sales_order_id] ?? null,
    })),
  } as ReturnType<typeof buildBoard>;
}

function renderPanel(
  batchId: string | null = null,
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
});

describe('AC-B2: the board loads a batch it names itself, no batch= needed', () => {
  it('fetches the batch the board names for the order, draws Was/Now and pre-marks it', async () => {
    getPlanningBoard.mockResolvedValue(
      withPendingBatch(
        buildBoard([demandA()], { today: TODAY, freeStock: {}, granularity: 'week' }),
        { 'so-381895': BATCH_A.id },
      ),
    );
    getPlanningChangeBatch.mockResolvedValue(BATCH_A);

    renderPanel(null, ['SO381895']);
    await screen.findByTestId('fulfilment-board-matrix');

    await waitFor(() => expect(getPlanningChangeBatch).toHaveBeenCalledWith(BATCH_A.id));
    expect(await screen.findByTestId('board-change-pcr-381895-1')).toBeInTheDocument();
  });
});

describe('AC-B3: two orders, two batches', () => {
  it('annotates both orders, fetches each batch once, and gives Confirm each own batch_id', async () => {
    getPlanningBoard.mockResolvedValue(
      withPendingBatch(
        buildBoard([demandA(), demandB()], {
          today: TODAY,
          freeStock: {},
          granularity: 'week',
        }),
        { 'so-381895': BATCH_A.id, 'so-381896': BATCH_B.id },
      ),
    );
    getPlanningChangeBatch.mockImplementation((id: string) =>
      Promise.resolve(id === BATCH_A.id ? BATCH_A : BATCH_B),
    );
    confirmMany.mockResolvedValue({
      results: [
        { pso_id: 'pso-so-381895', ok: true, decision_revision: 2 },
        { pso_id: 'pso-so-381896', ok: true, decision_revision: 2 },
      ],
    });

    renderPanel(null, ['SO381895', 'SO381896']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(await screen.findByTestId('board-change-pcr-381895-1')).toBeInTheDocument();
    expect(await screen.findByTestId('board-change-pcr-381896-1')).toBeInTheDocument();

    await waitFor(() => expect(getPlanningChangeBatch).toHaveBeenCalledTimes(2));
    expect(getPlanningChangeBatch).toHaveBeenCalledWith(BATCH_A.id);
    expect(getPlanningChangeBatch).toHaveBeenCalledWith(BATCH_B.id);

    fireEvent.click(await screen.findByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const byPso: Record<string, { batch_id?: string }> = Object.fromEntries(
      body.orders.map((order: { pso_id: string; batch_id?: string }) => [order.pso_id, order]),
    );
    expect(byPso['pso-so-381895']?.batch_id).toBe(BATCH_A.id);
    expect(byPso['pso-so-381896']?.batch_id).toBe(BATCH_B.id);
  });
});

describe('AC-B4: the URL batch still wins for a deep link', () => {
  it('fetches the URL batch even though the board names none for the order', async () => {
    getPlanningBoard.mockResolvedValue(
      buildBoard([demandA()], { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    getPlanningChangeBatch.mockResolvedValue(BATCH_A);

    renderPanel(BATCH_A.id, ['SO381895']);
    await screen.findByTestId('fulfilment-board-matrix');

    await waitFor(() => expect(getPlanningChangeBatch).toHaveBeenCalledWith(BATCH_A.id));
    expect(await screen.findByTestId('board-change-pcr-381895-1')).toBeInTheDocument();
  });
});

describe('AC-B6: an applied batch skips only its own order', () => {
  it('leaves the applied order out of the confirm-all body, the other order still posts', async () => {
    const appliedBatchA = {
      ...BATCH_A,
      orders: BATCH_A.orders.map((order) => ({
        ...order,
        rows: order.rows.map((row) => ({ ...row, applied_state: 'applied' as const })),
      })),
    };
    getPlanningBoard.mockResolvedValue(
      withPendingBatch(
        buildBoard([demandA(), demandB()], {
          today: TODAY,
          freeStock: {},
          granularity: 'week',
        }),
        { 'so-381895': appliedBatchA.id, 'so-381896': BATCH_B.id },
      ),
    );
    getPlanningChangeBatch.mockImplementation((id: string) =>
      Promise.resolve(id === appliedBatchA.id ? appliedBatchA : BATCH_B),
    );
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-381896', ok: true, decision_revision: 2 }],
    });

    renderPanel(null, ['SO381895', 'SO381896']);
    await screen.findByTestId('fulfilment-board-matrix');
    await screen.findByTestId('board-change-pcr-381896-1');

    fireEvent.click(await screen.findByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const psoIds = body.orders.map((order: { pso_id: string }) => order.pso_id);
    expect(psoIds).not.toContain('pso-so-381895');
    expect(psoIds).toContain('pso-so-381896');
  });
});
