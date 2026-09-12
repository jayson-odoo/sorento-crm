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
 * Seeds `BoardOrderStanding.pending_change_batch_id` onto the test-only `buildBoard`
 * fixture, keyed on `sales_order_id` - the field `FulfilmentBoardPanel` reads to union its
 * batch ids without a `batch=` URL param (AC-B1/AC-B2).
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

/**
 * Seeds a contribution's SERVER-PERSISTED save (S4/R-F), the same shape
 * `FulfilmentBoardPanel.test.tsx`'s own `allSaved` seeds - on BOTH `cells[].contributions`
 * and the board's top-level `contributions`, since Confirm reads the top-level list.
 * Lets a test give an ORDINARY (non-batch) line a decision without driving the real cell
 * dialog, exactly the way the reviewer's B1 scenario needs order B: "an ordinary
 * undecided line" the planner has already decided and saved.
 */
function withSavedContribution(
  board: ReturnType<typeof buildBoard>,
  matchSalesOrderId: string,
): ReturnType<typeof buildBoard> {
  const saved = {
    decision: { verdict: 'approved' as const },
    saved_by: 'Test Planner',
    saved_at: '2026-09-08T00:00:00Z',
  };
  const apply = (entry: { sales_order_id: string }) =>
    entry.sales_order_id === matchSalesOrderId ? { ...entry, draft: saved } : entry;
  return {
    ...board,
    cells: board.cells.map((cell) => ({
      ...cell,
      contributions: cell.contributions.map(apply),
    })),
    contributions: board.contributions.map(apply),
  } as ReturnType<typeof buildBoard>;
}

/**
 * B1 (blocker, reviewer's pass on 39a5d8b07): the confirm-all body must not carry a
 * body-level `batch_id` that disagrees with an order that has none of its own. Today the
 * panel still derives a single body-level `batch_id` from the ONE batch it loaded (only A
 * names one; B does not), so B's own entry silently inherits A's batch id on the wire even
 * though the board named no batch for it.
 */
describe('B1: the confirm-all body never lets a body-level batch_id contradict an order', () => {
  it('gives A its own batch_id, leaves B without one, and the two never disagree', async () => {
    getPlanningBoard.mockResolvedValue(
      withSavedContribution(
        withPendingBatch(
          buildBoard([demandA(), demandB()], {
            today: TODAY,
            freeStock: {},
            granularity: 'week',
          }),
          { 'so-381895': BATCH_A.id }, // B is NOT named by the board at all
        ),
        'so-381896',
      ),
    );
    getPlanningChangeBatch.mockResolvedValue(BATCH_A);
    confirmMany.mockResolvedValue({
      results: [
        { pso_id: 'pso-so-381895', ok: true, decision_revision: 2 },
        { pso_id: 'pso-so-381896', ok: true, decision_revision: 1 },
      ],
    });

    renderPanel(null, ['SO381895', 'SO381896']);
    await screen.findByTestId('fulfilment-board-matrix');
    await screen.findByTestId('board-change-pcr-381895-1');

    fireEvent.click(await screen.findByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const byPso: Record<string, { batch_id?: string | null }> = Object.fromEntries(
      body.orders.map((order: { pso_id: string; batch_id?: string | null }) => [
        order.pso_id,
        order,
      ]),
    );
    expect(byPso['pso-so-381895']?.batch_id).toBe(BATCH_A.id);
    expect(byPso['pso-so-381896']?.batch_id == null).toBe(true);

    // NOT (a body-level batch_id is set AND some order in the body lacks it).
    const bodyLevelBatchId = (body as { batch_id?: string | null }).batch_id;
    const someOrderLacksIt = body.orders.some(
      (order: { batch_id?: string | null }) => order.batch_id !== bodyLevelBatchId,
    );
    expect(Boolean(bodyLevelBatchId) && someOrderLacksIt).toBe(false);
  });
});

/**
 * S1 (should-fix, reviewer's pass on 39a5d8b07): a deep link's URL `batch=` can name an
 * APPLIED batch while the board itself names a PENDING one for the SAME order (the
 * planning-changes list still links the applied batch; the board now also unions in
 * whatever is pending). The union must not double-annotate the one cell, and Confirm must
 * judge the order by its PENDING rows, not by the applied batch the URL happened to carry.
 */
describe('S1: a URL-applied batch and a board-pending batch on the same order', () => {
  it('renders the changed cell once and does not skip the order from Confirm', async () => {
    const appliedBatchA = {
      ...BATCH_A,
      id: 'pcb-so381895-applied',
      applied_at: '2026-08-19T10:00:00Z',
      applied_by_name: 'Cyndi Tee',
      orders: BATCH_A.orders.map((order) => ({
        ...order,
        rows: order.rows.map((row) => ({ ...row, applied_state: 'applied' as const })),
      })),
    };

    getPlanningBoard.mockResolvedValue(
      withPendingBatch(
        buildBoard([demandA()], { today: TODAY, freeStock: {}, granularity: 'week' }),
        { 'so-381895': BATCH_A.id }, // the board itself names the PENDING batch
      ),
    );
    getPlanningChangeBatch.mockImplementation((id: string) =>
      Promise.resolve(id === appliedBatchA.id ? appliedBatchA : BATCH_A),
    );
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-381895', ok: true, decision_revision: 2 }],
    });

    // URL batchId names the APPLIED batch - a deep link from the planning-changes list.
    renderPanel(appliedBatchA.id, ['SO381895']);
    await screen.findByTestId('fulfilment-board-matrix');
    await screen.findAllByTestId('board-change-pcr-381895-1');

    expect(screen.getAllByTestId('board-change-pcr-381895-1')).toHaveLength(1);

    fireEvent.click(await screen.findByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const byPso: Record<string, { batch_id?: string | null }> = Object.fromEntries(
      body.orders.map((order: { pso_id: string; batch_id?: string | null }) => [
        order.pso_id,
        order,
      ]),
    );
    expect(byPso['pso-so-381895']).toBeDefined();
    expect(byPso['pso-so-381895']?.batch_id).toBe(BATCH_A.id);
  });
});
