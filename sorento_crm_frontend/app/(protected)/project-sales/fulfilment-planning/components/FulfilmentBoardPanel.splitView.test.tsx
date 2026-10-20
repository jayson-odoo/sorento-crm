/**
 * OI-SPLIT-VIEW (UAC A2, A3, A4, D1, D2) on the planning board panel: a split-edited line
 * counts in "N to confirm" and "Confirm (N)" once, is listed as "Split edits to confirm: line
 * <n> <item>", and the Confirm press posts its order even when no line of it is named. The
 * board gear carries "Split delivery <SO>" and "View splits <SO>" per order.
 *
 * Scaffolding mirrors `FulfilmentBoardPanel.autobatch.test.tsx` (same mocks, same `renderPanel`).
 * Red until the build: `split_edited` is not read, the gear items do not exist.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/fulfilment-planning',
  // R-J (List is now the default view): every spec here exercises the GRID matrix, so
  // `?view=grid` is seeded rather than clicking the Grid button in each test.
  useSearchParams: () => new URLSearchParams('view=grid&scope=all'),
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
const previewConfirmMany = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: vi.fn(),
  getSupply: vi.fn(),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  confirmMany: (...args: unknown[]) => confirmMany(...args),
  previewConfirmMany: (...args: unknown[]) => previewConfirmMany(...args),
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


const getLineSplits = vi.fn();
vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: (...args: unknown[]) => getLineSplits(...args),
  saveLineSplits: vi.fn(),
}));

vi.mock('./LineSplitDialog', () => ({
  LineSplitDialog: (props: { open: boolean; psoId: string }) =>
    props.open ? <div data-testid="line-split-dialog" data-pso={props.psoId} /> : null,
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import { MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE } from '../../_shared/__mocks__/planningChanges';

const TODAY = '2026-09-17';

const DECISION = {
  revision_no: 3,
  confirmed_at: '2026-09-16T02:00:00',
  timely_spo_qty: '0',
  reserve: [],
  borrow: [],
  buy_qty: '10',
};

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'Test Customer',
    project_sales_order_id: 'pso-so-1',
    project_line_id: 'pl-1-1',
    line_no: 1,
    item_code: 'ZZT-ITEM-1',
    qty: '10',
    required_date: '2026-09-20',
    fulfilment_location: 'BRW-IB',
    priority: null,
    decision: DECISION,
    ...overrides,
  } as BoardDemandLine;
}

/** Marks the lines `split_edited` on BOTH `cells[].contributions` and the top-level list. */
function withSplitEdited(board: ReturnType<typeof buildBoard>, lineIds: string[]) {
  const apply = <T extends { project_line_id?: string | null }>(entry: T): T =>
    entry.project_line_id && lineIds.includes(entry.project_line_id)
      ? { ...entry, split_edited: true }
      : entry;
  return {
    ...board,
    cells: board.cells.map((cell) => ({ ...cell, contributions: cell.contributions.map(apply) })),
    contributions: (board as unknown as { contributions?: { project_line_id?: string }[] })
      .contributions?.map(apply),
  } as unknown as ReturnType<typeof buildBoard>;
}

function renderPanel(soNumbers: string[] = ['SO000001']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} batchId={null} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

async function openBoardActions() {
  const trigger = await screen.findByRole('button', { name: 'Board actions' });
  fireEvent.keyDown(trigger, { key: 'Enter' });
  await screen.findByRole('menuitem', { name: 'Undo all' });
  return screen.getByRole('menu');
}

const TWO_ORDERS = [
  demand({}),
  demand({
    sales_order_id: 'so-2',
    so_number: 'SO000002',
    project_sales_order_id: 'pso-so-2',
    project_line_id: 'pl-2-1',
    line_no: 1,
    item_code: 'ZZT-ITEM-2',
  }),
];

beforeEach(() => {
  vi.clearAllMocks();
  previewConfirmMany.mockImplementation((body: { orders: { pso_id: string; lines: unknown[] }[] }) =>
    Promise.resolve({
      results: body.orders.map((order) => ({
        pso_id: order.pso_id, ok: true, preview: true, decision_revision: 4,
        lines_confirmed: [], lines_carried: 0, lines_held_back: [], lines_fulfilled_skipped: 0,
        inquiry_rows: [], transfers: [],
      })),
    }),
  );
});

describe('A2: a split-edited line counts once in the header and on Confirm', () => {
  it('a covered line with a saved split edit reads "1 to confirm" and Confirm (1)', async () => {
    getPlanningBoard.mockResolvedValue(
      withSplitEdited(
        buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
        ['pl-1-1'],
      ),
    );
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(await screen.findByTestId('board-confirm-summary')).toHaveTextContent('1 to confirm');
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)');
  });

  it('the same line without a split edit counts 0 (pins today)', async () => {
    getPlanningBoard.mockResolvedValue(
      buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(await screen.findByTestId('board-confirm-summary')).toHaveTextContent('0 to confirm');
  });
});

describe('A3: the card lists the lines whose split edits wait', () => {
  it('reads "Split edits to confirm: line 1 ZZT-ITEM-1"', async () => {
    getPlanningBoard.mockResolvedValue(
      withSplitEdited(
        buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
        ['pl-1-1'],
      ),
    );
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(await screen.findByText('Split edits to confirm: line 1 ZZT-ITEM-1')).toBeInTheDocument();
  });

  it('is not there when nothing is split-edited', async () => {
    getPlanningBoard.mockResolvedValue(
      buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.queryByText(/Split edits to confirm/)).not.toBeInTheDocument();
  });
});

describe('A4: Confirm posts the order of a split-edited line even with no line of its own', () => {
  it('posts pso-so-1 with an empty lines list', async () => {
    getPlanningBoard.mockResolvedValue(
      withSplitEdited(
        buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
        ['pl-1-1'],
      ),
    );
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-1', ok: true, decision_revision: 4, lines_confirmed: [] }],
    });
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    fireEvent.click(screen.getByTestId('board-confirm'));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const sent = body.orders.find((order: { pso_id: string }) => order.pso_id === 'pso-so-1');
    expect(sent, JSON.stringify(body)).toBeDefined();
    expect(sent.lines).toEqual([]);
  });
});

describe('D1 / D2: the board gear carries Split delivery and View splits per order', () => {
  it('lists "Split delivery <SO>" and "View splits <SO>" for each order', async () => {
    getPlanningBoard.mockResolvedValue(
      buildBoard(TWO_ORDERS, { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel(['SO000001', 'SO000002']);
    const menu = await openBoardActions();
    for (const so of ['SO000001', 'SO000002']) {
      expect(within(menu).getByRole('menuitem', { name: `Split delivery ${so}` })).toBeInTheDocument();
      expect(within(menu).getByRole('menuitem', { name: `View splits ${so}` })).toBeInTheDocument();
    }
  });

  it('"Split delivery SO000001" opens the split sheet for that order', async () => {
    getPlanningBoard.mockResolvedValue(
      buildBoard(TWO_ORDERS, { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel(['SO000001', 'SO000002']);
    const menu = await openBoardActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Split delivery SO000001' }));
    const dialog = await screen.findByTestId('line-split-dialog');
    expect(dialog).toHaveAttribute('data-pso', 'pso-so-1');
  });

  it('"View splits SO000001" reads the order and opens "SO000001: splits"', async () => {
    const view = (qty: string) => ({
      status: 'confirmed', revision_no: 3, confirmed_on: '2026-10-19',
      base_qty: '417', base_date: '2026-10-20', now_qty: '14', now_date: '2026-09-20',
      total_qty: '417',
      rows: [{
        qty, delivery_date: '2026-09-20', change: 'ADVANCE', sits_on: 'own',
        sits_on_line_no: 480, remark: '', is_cancel: false, changed: false, was_qty: null,
        was_date: null,
      }],
    });
    getLineSplits.mockResolvedValue({
      pso_id: 'pso-so-1', so_number: 'SO000001', customer: null, project: null,
      lines: [
        { line_id: 'pl-1-1', line_no: 480, item_code: 'CSK14B', split_view: view('14') },
        { line_id: 'pl-1-2', line_no: 752, item_code: 'CSK14B', split_view: view('37') },
        { line_id: 'pl-1-3', line_no: 608, item_code: 'CSK14B', split_view: null },
      ],
    });
    getPlanningBoard.mockResolvedValue(
      buildBoard(TWO_ORDERS, { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel(['SO000001', 'SO000002']);
    const menu = await openBoardActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'View splits SO000001' }));
    const dialog = await screen.findByRole('dialog');
    expect(getLineSplits).toHaveBeenCalledWith('pso-so-1');
    expect(within(dialog).getByText('SO000001: splits')).toBeInTheDocument();
    expect(dialog.textContent).toContain('2 split lines');
    expect(dialog.textContent).toContain('Line 480 CSK14B');
    expect(dialog.textContent).not.toContain('Line 608');
  });
});

describe('review round 1 (UAC A3): the list names exactly the lines the count includes', () => {
  it('a split-edited line with a stale draft counts exactly 1 and is listed (review round 2)', async () => {
    const board = withSplitEdited(
      buildBoard([demand()], { today: TODAY, freeStock: {}, granularity: 'week' }),
      ['pl-1-1'],
    );
    const stale = (entry: { project_line_id?: string | null }) =>
      entry.project_line_id === 'pl-1-1'
        ? {
            ...entry,
            draft: {
              decision: { verdict: 'approved' },
              saved_by: 'Test Planner',
              saved_at: '2026-09-08T00:00:00Z',
              stale: true,
            },
          }
        : entry;
    const staleBoard = {
      ...board,
      cells: board.cells.map((c) => ({ ...c, contributions: c.contributions.map(stale) })),
      contributions: (board as unknown as { contributions?: { project_line_id?: string }[] })
        .contributions?.map(stale),
    } as unknown as ReturnType<typeof buildBoard>;
    getPlanningBoard.mockResolvedValue(staleBoard);
    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    const summary = await screen.findByTestId('board-confirm-summary');
    const counted = Number((summary.textContent ?? '').match(/(\d+) to confirm/)?.[1]);
    const listed = screen.queryByText('Split edits to confirm: line 1 ZZT-ITEM-1') !== null;
    expect(counted).toBe(1);
    expect(listed).toBe(true);
    // and the Confirm button agrees with the count
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(`Confirm (${counted})`);
  });
});


describe('review round 3 (UAC A12): a pending AutoCount batch on OTHER lines does not hold back a split edit', () => {
  // MOCK batch: SO381895, its pending row names pl-381895-1. The split-edited line is pl-381895-9.
  const BATCH = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE;
  const named = demand({
    sales_order_id: 'so-381895', so_number: 'SO381895', project_sales_order_id: 'pso-so-381895',
    project_line_id: 'pl-381895-1', line_no: 1, item_code: 'SRTWCX7405-RL-S-PJ',
  });
  const edited = demand({
    sales_order_id: 'so-381895', so_number: 'SO381895', project_sales_order_id: 'pso-so-381895',
    project_line_id: 'pl-381895-9', line_no: 2, item_code: 'SRTWCX-OTHER-ITEM',
  });

  function batchBoard() {
    const board = withSplitEdited(
      buildBoard([named, edited], { today: TODAY, freeStock: {}, granularity: 'week' }),
      ['pl-381895-9'],
    );
    return {
      ...board,
      orders: board.orders.map((order) => ({ ...order, pending_change_batch_id: BATCH.id })),
    } as unknown as ReturnType<typeof buildBoard>;
  }

  it('the split-edited line counts 1, is listed, and the Confirm press posts its order with the batch id', async () => {
    getPlanningBoard.mockResolvedValue(batchBoard());
    getPlanningChangeBatch.mockResolvedValue(BATCH);
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-381895', ok: true, decision_revision: 4, lines_confirmed: [] }],
    });
    renderPanel(['SO381895']);
    await screen.findByTestId('fulfilment-board-matrix');
    expect(await screen.findByTestId('board-confirm-summary')).toHaveTextContent('1 to confirm');
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)');
    expect(screen.getByText('Split edits to confirm: line 2 SRTWCX-OTHER-ITEM')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    fireEvent.click(screen.getByTestId('board-confirm'));
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const sent = body.orders.find((order: { pso_id: string }) => order.pso_id === 'pso-so-381895');
    expect(sent, JSON.stringify(body)).toBeDefined();
    expect(sent.lines).toEqual([]);
    expect(sent.batch_id).toBe(BATCH.id);
  });
});


describe('review round 3 (UAC B8): Escape on the gear\'s View splits popup returns focus to the gear', () => {
  it('focus is on the Board actions button after Escape', async () => {
    getLineSplits.mockResolvedValue({
      pso_id: 'pso-so-1', so_number: 'SO000001', customer: null, project: null, lines: [],
    });
    getPlanningBoard.mockResolvedValue(
      buildBoard(TWO_ORDERS, { today: TODAY, freeStock: {}, granularity: 'week' }),
    );
    renderPanel(['SO000001', 'SO000002']);
    const menu = await openBoardActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'View splits SO000001' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Board actions' })),
    );
  });
});
