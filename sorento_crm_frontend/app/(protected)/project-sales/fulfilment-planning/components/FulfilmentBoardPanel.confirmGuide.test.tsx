/**
 * OI-SPLIT-GUIDE (UAC A to D) on the planning board panel: Confirm (N) opens a guided dialog
 * (Split, Review, Confirm) instead of posting. Tests drive the panel, not the dialog's props, and
 * use the test ids of `PLAN-oi-split-guide-20oct.md` ("Test ids").
 *
 * Scaffolding mirrors `FulfilmentBoardPanel.splitView.test.tsx`. Red until the build: the guide
 * does not exist, so Confirm (N) still posts at once.
 */
import React from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
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
  // Save re-reads like the real sheet (its mutation invalidates the board and the split reads);
  // Close leaves without saving.
  LineSplitDialog: function MockLineSplitDialog(props: {
    open: boolean;
    psoId: string;
    onOpenChange: (open: boolean) => void;
  }) {
    const client = useQueryClient();
    return props.open ? (
      <div data-testid="line-split-dialog" data-pso={props.psoId}>
        <button
          type="button"
          data-testid="line-split-dialog-save"
          onClick={() => {
            void client.invalidateQueries();
            props.onOpenChange(false);
          }}
        >
          mock save
        </button>
        <button
          type="button"
          data-testid="line-split-dialog-close"
          onClick={() => props.onOpenChange(false)}
        >
          mock close
        </button>
      </div>
    ) : null;
  },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import { wireLine, wireSplit } from '@/test-mocks/lineSplitSheetKit';
import {
  guideControl,
  openConfirmGuide,
  walkConfirmGuide,
  walkToConfirmStep,
} from '@/test-mocks/confirmGuide';
import { toast } from '@/lib/toast';

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

const SO1_L1 = demand({});
const SO1_L2 = demand({ project_line_id: 'pl-1-2', line_no: 2, item_code: 'ZZT-ITEM-1B' });
const SO2_L1 = demand({
  sales_order_id: 'so-2',
  so_number: 'SO000002',
  project_sales_order_id: 'pso-so-2',
  project_line_id: 'pl-2-1',
  line_no: 1,
  item_code: 'ZZT-ITEM-2',
});

type Board = ReturnType<typeof buildBoard>;

function mapContributions(board: Board, fn: (entry: Record<string, unknown>) => Record<string, unknown>) {
  const apply = (entry: unknown) => fn(entry as Record<string, unknown>);
  return {
    ...board,
    cells: board.cells.map((cell) => ({ ...cell, contributions: cell.contributions.map(apply) })),
    contributions: (board as unknown as { contributions?: unknown[] }).contributions?.map(apply),
  } as unknown as Board;
}

/** `split_edited` on the named lines (the board's "Split edits to confirm" list). */
function withSplitEdited(board: Board, lineIds: string[]) {
  return mapContributions(board, (entry) =>
    lineIds.includes(String(entry.project_line_id)) ? { ...entry, split_edited: true } : entry,
  );
}

/** A saved approved decision draft on the named lines (a saved line the press names). */
function withDraft(board: Board, lineIds: string[]) {
  return mapContributions(board, (entry) =>
    lineIds.includes(String(entry.project_line_id))
      ? {
          ...entry,
          draft: {
            decision: { verdict: 'approved' },
            saved_by: 'Test Planner',
            saved_at: '2026-09-08T00:00:00Z',
          },
        }
      : entry,
  );
}

function boardOf(lines: BoardDemandLine[]) {
  return buildBoard(lines, { today: TODAY, freeStock: {}, granularity: 'week' });
}

/** One saved-edit board: SO000001 line 1 is split-edited, line 2 (same order) is not. */
function oneEditedBoard() {
  return withSplitEdited(boardOf([SO1_L1, SO1_L2, SO2_L1]), ['pl-1-1']);
}

/** Both orders carry a saved split edit. */
function twoEditedBoard() {
  return withSplitEdited(boardOf([SO1_L1, SO1_L2, SO2_L1]), ['pl-1-1', 'pl-2-1']);
}

/** The split read of an order: `edited` ids are 'saved', the others 'confirmed' (applied). */
function splitRead(
  psoId: string,
  so: string,
  lines: { id: string; no: number; item: string; edited: boolean }[],
) {
  return {
    pso_id: psoId,
    so_number: so,
    so_date: '2026-09-03',
    customer: 'Test Customer',
    project: 'Test Project',
    confirmed_at: null,
    lines: lines.map((l) =>
      wireLine(l.no, l.item, 10, '2026-09-20', {
        line_id: l.id,
        now_qty: 10,
        split_state: l.edited ? 'acting' : 'applied',
        split_view: { status: l.edited ? 'saved' : 'confirmed' },
        splits: [
          wireSplit(`${l.id}-a`, 6, '2026-09-20', l.id),
          wireSplit(`${l.id}-b`, 4, '2026-10-20', null),
        ],
      }),
    ),
  };
}

const SO1_READ = () =>
  splitRead('pso-so-1', 'SO000001', [
    { id: 'pl-1-1', no: 1, item: 'ZZT-ITEM-1', edited: true },
    { id: 'pl-1-2', no: 2, item: 'ZZT-ITEM-1B', edited: false },
  ]);
const SO2_READ = () =>
  splitRead('pso-so-2', 'SO000002', [{ id: 'pl-2-1', no: 1, item: 'ZZT-ITEM-2', edited: true }]);

function serveSplits(reads: Record<string, unknown> = {}) {
  getLineSplits.mockImplementation((psoId: string) =>
    Promise.resolve(
      reads[psoId] ?? (psoId === 'pso-so-1' ? SO1_READ() : psoId === 'pso-so-2' ? SO2_READ() : null),
    ),
  );
}

type Row = Record<string, unknown>;

function row(over: Row = {}): Row {
  return {
    line_no: 1,
    item_code: 'ZZT-ITEM-1',
    verb: 'ORDER',
    is_new: true,
    qty: '12',
    delivery_date: '2026-09-20',
    stock_location: 'BRW-IB',
    note: null,
    autocount_change: null,
    ...over,
  };
}

/** The dry run answers every order ok with the rows given per pso (none by default). */
function dryRunAnswers(perPso: Record<string, { rows?: Row[]; transfers?: Row[]; error?: string }> = {}) {
  previewConfirmMany.mockImplementation((body: { orders: { pso_id: string }[] }) =>
    Promise.resolve({
      results: body.orders.map((order) => {
        const spec = perPso[order.pso_id] ?? {};
        if (spec.error) {
          return { pso_id: order.pso_id, ok: false, preview: true, error: spec.error };
        }
        return {
          pso_id: order.pso_id,
          ok: true,
          preview: true,
          decision_revision: 4,
          lines_confirmed: [],
          lines_carried: 0,
          lines_held_back: [],
          lines_fulfilled_skipped: 0,
          inquiry_rows: spec.rows ?? [],
          transfers: spec.transfers ?? [],
        };
      }),
    }),
  );
}

function confirmAnswers() {
  confirmMany.mockImplementation((body: { orders: { pso_id: string }[] }) =>
    Promise.resolve({
      results: body.orders.map((order) => ({
        pso_id: order.pso_id,
        ok: true,
        decision_revision: 4,
        lines_confirmed: [],
      })),
    }),
  );
}

function renderPanel(soNumbers: string[] = ['SO000001', 'SO000002']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} batchId={null} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

async function mountWith(board: Board, soNumbers?: string[]) {
  getPlanningBoard.mockResolvedValue(board);
  renderPanel(soNumbers);
  await screen.findByTestId('fulfilment-board-matrix');
  await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
}

const pages = () => screen.queryAllByTestId('confirm-guide-split-page');
const click = (id: string) => fireEvent.click(screen.getByTestId(id));

beforeEach(() => {
  vi.clearAllMocks();
  serveSplits();
  dryRunAnswers();
  confirmAnswers();
});

// ---------------------------------------------------------------------------
// T-FE1: A1, A2, A3
// ---------------------------------------------------------------------------

describe('T-FE1 (A1 A2 A3): Confirm (N) opens the guide and posts nothing', () => {
  it('opens the guide on press, with no dry run and no confirm call yet', async () => {
    await mountWith(oneEditedBoard());
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)');
    await openConfirmGuide();
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
    expect(confirmMany).not.toHaveBeenCalled();
    expect(previewConfirmMany).not.toHaveBeenCalled();
  });

  it('names the orders of this Confirm in the title and draws the three steps', async () => {
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    expect(screen.getByTestId('confirm-guide')).toHaveTextContent('Confirm SO000001, SO000002');
    const steps = screen.getByTestId('confirm-guide-steps');
    expect(within(steps).getAllByRole('listitem')).toHaveLength(3);
  });

  it('Cancel closes the guide and writes nothing', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    click('confirm-guide-cancel');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
    expect(previewConfirmMany).not.toHaveBeenCalled();
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)');
  });

  it('Escape closes the guide and writes nothing', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    fireEvent.keyDown(screen.getByTestId('confirm-guide'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('Escape and Cancel after the dry run still write nothing', async () => {
    await mountWith(withDraft(boardOf([SO1_L1]), ['pl-1-1']), ['SO000001']);
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-review');
    fireEvent.keyDown(screen.getByTestId('confirm-guide'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('at Confirm (0) the button is disabled and no guide is reachable', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([SO1_L1]));
    renderPanel(['SO000001']);
    await screen.findByTestId('fulfilment-board-matrix');
    const button = await screen.findByTestId('board-confirm');
    expect(button).toHaveTextContent('Confirm (0)');
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T-FE2: B1, B2, B3, B6
// ---------------------------------------------------------------------------

describe('T-FE2 (B1 B2 B3 B6): split pages are the orders with a saved split edit, and only those lines', () => {
  it('two orders, only SO000001 has a saved split edit: exactly one split page', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await waitFor(() => expect(pages()).toHaveLength(1));
    expect(pages()[0]).toHaveAttribute('data-so', 'SO000001');
    expect(getLineSplits).not.toHaveBeenCalledWith('pso-so-2');
  });

  it('shows the saved split edit as a read-only sheet block and not the unchanged line', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(await within(page).findByTestId('split-line-1')).toBeInTheDocument();
    expect(within(page).queryByTestId('split-line-2')).not.toBeInTheDocument();
    expect(page.querySelectorAll('input, [data-drag-handle]')).toHaveLength(0);
  });

  it('both orders edited: two pages in board order, SO000001 first', async () => {
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    const first = await screen.findByTestId('confirm-guide-split-page');
    expect(first).toHaveAttribute('data-so', 'SO000001');
    fireEvent.click(screen.getByTestId('confirm-guide-next'));
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
  });

  it('the page header names the order, the badge, the count (singular) and one CTA', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(page).toHaveTextContent('SO000001');
    expect(page).toHaveTextContent('Saved, not confirmed');
    expect(page.textContent).toMatch(/1 split line(?!s)/);
    expect(within(page).getByTestId('confirm-guide-split-edit')).toHaveTextContent(
      'Split delivery SO000001',
    );
    expect(within(page).getAllByRole('button', { name: /^Split delivery/ })).toHaveLength(1);
  });

  it('no order has a saved split edit: the guide opens at Review with two steps', async () => {
    await mountWith(withDraft(boardOf([SO1_L1, SO2_L1]), ['pl-1-1']));
    await openConfirmGuide();
    expect(await screen.findByTestId('confirm-guide-review')).toBeInTheDocument();
    expect(pages()).toHaveLength(0);
    expect(within(screen.getByTestId('confirm-guide-steps')).getAllByRole('listitem')).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// T-FE3: B4, B5, B7
// ---------------------------------------------------------------------------

describe('T-FE3 (B4 B5 B7): walking, editing and failing a split page', () => {
  it('Next walks the pages one by one and Review comes only after the last', async () => {
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    expect(screen.getByTestId('confirm-guide-next')).toHaveTextContent('Next order');
    expect(screen.queryByTestId('confirm-guide-review')).not.toBeInTheDocument();
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(screen.queryByTestId('confirm-guide-review')).not.toBeInTheDocument();
    expect(previewConfirmMany).not.toHaveBeenCalled();
    expect(screen.getByTestId('confirm-guide-next')).toHaveTextContent('Next: Review');
    click('confirm-guide-next');
    expect(await screen.findByTestId('confirm-guide-review')).toBeInTheDocument();
  });

  it('Back returns to the previous page', async () => {
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    click('confirm-guide-back');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001'),
    );
  });

  it('the CTA opens the edit sheet for that order on top of the guide', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-split-edit');
    const edit = await screen.findByTestId('line-split-dialog');
    expect(edit).toHaveAttribute('data-pso', 'pso-so-1');
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
  });

  it('closing the edit sheet without saving changes nothing', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-split-edit');
    await screen.findByTestId('line-split-dialog');
    click('line-split-dialog-close');
    await waitFor(() => expect(screen.queryByTestId('line-split-dialog')).not.toBeInTheDocument());
    const page = screen.getByTestId('confirm-guide-split-page');
    expect(page).toHaveAttribute('data-so', 'SO000001');
    expect(await within(page).findByTestId('split-line-1')).toBeInTheDocument();
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('after Save the page re-reads: an order left with no saved edit drops, the next page shows', async () => {
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-split-edit');
    await screen.findByTestId('line-split-dialog');
    // The planner's Save put SO000001 back to its applied plan: nothing left to confirm there.
    getPlanningBoard.mockResolvedValue(withSplitEdited(boardOf([SO1_L1, SO1_L2, SO2_L1]), ['pl-2-1']));
    serveSplits({
      'pso-so-1': splitRead('pso-so-1', 'SO000001', [
        { id: 'pl-1-1', no: 1, item: 'ZZT-ITEM-1', edited: false },
        { id: 'pl-1-2', no: 2, item: 'ZZT-ITEM-1B', edited: false },
      ]),
    });
    click('line-split-dialog-save');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(pages()).toHaveLength(1);
  });

  it('after Save the page shows the changed values', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    const before = await screen.findByTestId('confirm-guide-split-page');
    await within(before).findByTestId('split-line-1');
    const textBefore = before.textContent;
    click('confirm-guide-split-edit');
    await screen.findByTestId('line-split-dialog');
    serveSplits({
      'pso-so-1': {
        ...SO1_READ(),
        lines: [
          wireLine(1, 'ZZT-ITEM-1', 10, '2026-09-20', {
            line_id: 'pl-1-1',
            split_state: 'acting',
            split_view: { status: 'saved' },
            splits: [
              wireSplit('x1', 3, '2026-09-20', 'pl-1-1'),
              wireSplit('x2', 7, '2026-12-21', null),
            ],
          }),
        ],
      },
    });
    click('line-split-dialog-save');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page').textContent).not.toBe(textBefore),
    );
    expect(screen.getByTestId('confirm-guide-split-page').textContent).toContain('21/12/2026');
  });

  it('a split sheet that fails to load says so with Retry, Next off, Back and Cancel working', async () => {
    getLineSplits.mockRejectedValue(new Error('boom'));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    expect(await screen.findByTestId('confirm-guide-split-error')).toBeInTheDocument();
    expect(screen.queryByTestId('confirm-guide-next') ?? { disabled: true }).toHaveProperty(
      'disabled',
      true,
    );
    getLineSplits.mockImplementation(() => Promise.resolve(SO1_READ()));
    click('confirm-guide-split-retry');
    await waitFor(() =>
      expect(screen.queryByTestId('confirm-guide-split-error')).not.toBeInTheDocument(),
    );
    expect(await screen.findByTestId('split-line-1')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('Cancel works on a split page that failed to load', async () => {
    getLineSplits.mockRejectedValue(new Error('boom'));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-error');
    click('confirm-guide-cancel');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// T-FE4: C1 to C7
// ---------------------------------------------------------------------------

describe('T-FE4 (C1 to C7): Review shows what purchasing will get', () => {
  it('runs the dry run once on entering Review, with the body the press builds, and shows a loading state', async () => {
    let release: (value: unknown) => void = () => undefined;
    previewConfirmMany.mockImplementation(
      () => new Promise((resolve) => { release = resolve; }),
    );
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    expect(previewConfirmMany).not.toHaveBeenCalled();
    click('confirm-guide-next');
    await waitFor(() => expect(previewConfirmMany).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('confirm-guide-review')).toBeInTheDocument();
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    const [body] = previewConfirmMany.mock.calls[0];
    expect(body.orders).toHaveLength(1);
    expect(body.orders[0].pso_id).toBe('pso-so-1');
    expect(body.orders[0].lines).toEqual([]);
    release({ results: [{ pso_id: 'pso-so-1', ok: true, preview: true, inquiry_rows: [], transfers: [] }] });
    await screen.findByTestId('confirm-guide-nothing');
  });

  it('runs the dry run again on every re-entry of Review (Back, then Next)', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-review');
    await waitFor(() => expect(previewConfirmMany).toHaveBeenCalledTimes(1));
    click('confirm-guide-back');
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await waitFor(() => expect(previewConfirmMany).toHaveBeenCalledTimes(2));
    expect(previewConfirmMany.mock.calls[1][0]).toEqual(previewConfirmMany.mock.calls[0][0]);
  });

  it('lists each order\'s inquiry rows with line, item, location and qty, and its transfers', async () => {
    dryRunAnswers({
      'pso-so-1': {
        rows: [row(), row({ line_no: 3, item_code: 'ZZT-ITEM-3', qty: '5', stock_location: 'KL-HQ' })],
        transfers: [
          { line_no: 1, is_new: true, kind: 'borrow', qty: '4', from_location: 'KL-HQ', to_location: 'BRW-IB' },
        ],
      },
      'pso-so-2': { rows: [] },
    });
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    const orders = await screen.findAllByTestId('confirm-guide-review-order');
    const so1 = orders.find((el) => el.getAttribute('data-so') === 'SO000001')!;
    const so2 = orders.find((el) => el.getAttribute('data-so') === 'SO000002')!;
    const rows = within(so1).getAllByTestId('confirm-guide-review-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('ZZT-ITEM-1');
    expect(rows[0]).toHaveTextContent('BRW-IB');
    expect(rows[1]).toHaveTextContent('ZZT-ITEM-3');
    expect(rows[1]).toHaveTextContent('KL-HQ');
    expect(so1).toHaveTextContent('borrow');
    expect(so1).toHaveTextContent('4');
    expect(within(so2).getByTestId('confirm-guide-nothing')).toHaveTextContent(
      'Nothing to send to purchasing',
    );
  });

  it.each([
    ['cancelled', 'AutoCount cancelled'],
    ['qty', 'AutoCount changed qty'],
    ['date', 'AutoCount changed date'],
    ['qty_date', 'AutoCount changed qty and date'],
  ])('a row with autocount_change %s carries the label "%s"', async (cause, label) => {
    dryRunAnswers({
      'pso-so-1': { rows: [row({ line_no: 2, item_code: 'ZZT-ITEM-1B', autocount_change: cause })] },
    });
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    const found = await screen.findByTestId('confirm-guide-autocount');
    expect(found).toHaveTextContent(label);
    expect(found.textContent?.trim()).toBe(label);
    expect(found.closest('[data-testid="confirm-guide-review-row"]')).toHaveTextContent('ZZT-ITEM-1B');
  });

  it('a row from a saved line carries no AutoCount label', async () => {
    dryRunAnswers({ 'pso-so-1': { rows: [row({ autocount_change: null })] } });
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findAllByTestId('confirm-guide-review-row');
    expect(screen.queryByTestId('confirm-guide-autocount')).not.toBeInTheDocument();
  });

  it('an order the dry run refuses shows its reason, and step 3 leaves it out', async () => {
    dryRunAnswers({
      'pso-so-1': { rows: [row()] },
      'pso-so-2': { error: 'Line 1 has no supply.' },
    });
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    const refused = await screen.findByTestId('confirm-guide-refused');
    expect(refused).toHaveTextContent('Line 1 has no supply.');
    const control = (await guideControl())!;
    click('confirm-guide-next');
    const confirm = await screen.findByTestId('confirm-guide-confirm');
    expect(control.getAttribute('data-testid')).toBe('confirm-guide-next');
    expect(confirm).toHaveTextContent('Confirm 1 order');
    expect(screen.getByTestId('confirm-guide')).toHaveTextContent('SO000001 (1 row)');
    expect(screen.getByTestId('confirm-guide')).not.toHaveTextContent('SO000002 (');
  });

  it('a dry run that fails shows the error with Retry and Back, and Confirm cannot be reached', async () => {
    previewConfirmMany.mockRejectedValue(new Error('network down'));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    expect(await screen.findByTestId('confirm-guide-review-error')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-review-retry')).toBeEnabled();
    expect(screen.getByTestId('confirm-guide-back')).toBeEnabled();
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    const next = screen.queryByTestId('confirm-guide-next') as HTMLButtonElement | null;
    expect(next === null || next.disabled).toBe(true);
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('Retry runs the dry run again and, once it answers, Confirm can be reached', async () => {
    previewConfirmMany.mockRejectedValueOnce(new Error('network down'));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-review-error');
    dryRunAnswers({ 'pso-so-1': { rows: [row()] } });
    click('confirm-guide-review-retry');
    await waitFor(() => expect(previewConfirmMany).toHaveBeenCalledTimes(2));
    await screen.findAllByTestId('confirm-guide-review-row');
    expect(screen.queryByTestId('confirm-guide-review-error')).not.toBeInTheDocument();
    expect(await screen.findByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('every order refused: Review says nothing can be confirmed and Confirm cannot be reached', async () => {
    dryRunAnswers({
      'pso-so-1': { error: 'Line 1 has no supply.' },
      'pso-so-2': { error: 'Line 1 is held.' },
    });
    await mountWith(twoEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    const refusals = await screen.findAllByTestId('confirm-guide-refused');
    expect(refusals.map((el) => el.textContent).join(' ')).toContain('Line 1 has no supply.');
    expect(refusals.map((el) => el.textContent).join(' ')).toContain('Line 1 is held.');
    expect(screen.getByTestId('confirm-guide-review')).toHaveTextContent(/nothing can be confirmed/i);
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    const next = screen.queryByTestId('confirm-guide-next') as HTMLButtonElement | null;
    expect(next === null || next.disabled).toBe(true);
    // C7: Cancel closes, nothing is posted, no result card.
    click('confirm-guide-cancel');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
    expect(screen.queryByTestId('board-confirm-results')).not.toBeInTheDocument();
  });

  it('a row whose state is cancelled shows CANCEL in its remark cell', async () => {
    dryRunAnswers({
      'pso-so-1': {
        rows: [
          row({ line_no: 2, item_code: 'ZZT-ITEM-1B', state: 'cancelled', autocount_change: 'qty' }),
          row({ state: 'raised' }),
        ],
      },
    });
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    const rows = await screen.findAllByTestId('confirm-guide-review-row');
    const cancelled = rows.find((el) => el.textContent?.includes('ZZT-ITEM-1B'))!;
    expect(cancelled).toHaveTextContent('CANCEL');
    const raised = rows.find((el) => el !== cancelled)!;
    expect(raised).not.toHaveTextContent('CANCEL');
  });

  it('some orders refused and some ok: Confirm stays reachable', async () => {
    dryRunAnswers({
      'pso-so-1': { rows: [row()] },
      'pso-so-2': { error: 'Line 1 has no supply.' },
    });
    await mountWith(twoEditedBoard());
    const confirm = await walkToConfirmStep();
    expect(confirm).not.toBeNull();
    expect(confirm).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// T-FE5: D1 to D3
// ---------------------------------------------------------------------------

describe('T-FE5 (D1 D2 D3): the Confirm step posts what today\'s press posts', () => {
  it('summarises the orders and rows and offers one button', async () => {
    dryRunAnswers({
      'pso-so-1': { rows: [row()] },
      'pso-so-2': { rows: Array.from({ length: 9 }, (_, i) => row({ line_no: i + 1 })) },
    });
    await mountWith(twoEditedBoard());
    const confirm = (await walkToConfirmStep())!;
    const guide = screen.getByTestId('confirm-guide');
    expect(guide).toHaveTextContent(
      '2 orders: SO000001 (1 row), SO000002 (9 rows). Nothing has been sent yet.',
    );
    expect(confirm).toHaveTextContent('Confirm 2 orders');
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('posts the dry run\'s body (same orders, same lines) once, shows the result card and closes the guide', async () => {
    await mountWith(oneEditedBoard());
    await walkConfirmGuide();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    expect(previewConfirmMany).toHaveBeenCalledTimes(1);
    const [dryBody] = previewConfirmMany.mock.calls[0];
    const [body] = confirmMany.mock.calls[0];
    expect(body).not.toHaveProperty('preview');
    expect(body).toEqual(dryBody);
    expect(body.orders.map((o: { pso_id: string }) => o.pso_id)).toEqual(['pso-so-1']);
    expect(body.orders[0].lines).toEqual([]);
    expect(await screen.findByTestId('board-confirm-results')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
  });

  it('is disabled while posting, so a second click posts nothing more', async () => {
    let finish: (value: unknown) => void = () => undefined;
    confirmMany.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await mountWith(oneEditedBoard());
    const confirm = (await walkToConfirmStep())!;
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('confirm-guide-confirm')).toBeDisabled());
    fireEvent.click(screen.getByTestId('confirm-guide-confirm'));
    expect(confirmMany).toHaveBeenCalledTimes(1);
    finish({ results: [{ pso_id: 'pso-so-1', ok: true, decision_revision: 4, lines_confirmed: [] }] });
    await screen.findByTestId('board-confirm-results');
  });

  it('a failed post toasts the error and leaves the guide open at step 3 with Confirm enabled again', async () => {
    confirmMany.mockRejectedValue(new Error('server said no'));
    await mountWith(oneEditedBoard());
    const confirm = (await walkToConfirmStep())!;
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('confirm-guide-confirm')).toBeEnabled());
  });
});
