/**
 * OI-SPLIT-GUIDE (UAC A to F) on the planning board panel: Confirm (N) opens a guided dialog
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
const putLineDraft = vi.fn();

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
  putLineDraft: (...args: unknown[]) => putLineDraft(...args),
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
const saveLineSplits = vi.fn();
vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: (...args: unknown[]) => getLineSplits(...args),
  saveLineSplits: (...args: unknown[]) => saveLineSplits(...args),
}));

vi.mock('./LineSplitDialog', () => ({
  // Save re-reads like the real sheet (its mutation invalidates the board and the split reads);
  // Close leaves without saving.
  LineSplitDialog: function MockLineSplitDialog(props: {
    open: boolean;
    psoId: string;
    onlyLineIds?: ReadonlySet<string>;
    onOpenChange: (open: boolean) => void;
  }) {
    const client = useQueryClient();
    return props.open ? (
      <div
        data-testid="line-split-dialog"
        data-pso={props.psoId}
        data-only-lines={props.onlyLineIds ? [...props.onlyLineIds].sort().join(',') : ''}
      >
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
import { addBtn, qty, splitLine, typeDate, typeQty, wireLine, wireSplit } from '@/test-mocks/lineSplitSheetKit';
import { openConfirmGuide, walkConfirmGuide, walkToConfirmStep } from '@/test-mocks/confirmGuide';
import { toast } from '@/lib/toast';
import userEvent from '@testing-library/user-event';

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


/*
 * Round 3 (UAC F, owner rework): the review IS the split view. Two steps, "Review split" then
 * "Confirm". One page per order of this Confirm, listing every line the Confirm covers: a split
 * line with its split rows, an unsplit line as ONE row whose Remark is the server's `saved_remark`
 * (the purchasing email's words). No dry-run table, no transfers, no AutoCount labels.
 */
const SO1_L1 = demand({});
const SO1_L2 = demand({ project_line_id: 'pl-1-2', line_no: 2, item_code: 'ZZT-ITEM-1B' });
const SO1_L3 = demand({ project_line_id: 'pl-1-3', line_no: 3, item_code: 'ZZT-ITEM-1C' });
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
function withDraft(board: Board, lineIds: string[], remarks: Record<string, string> = {}) {
  return mapContributions(board, (entry) =>
    lineIds.includes(String(entry.project_line_id))
      ? {
          ...entry,
          // F10: the email's words ride the board's own line data (`saved_remark`).
          saved_remark: remarks[String(entry.project_line_id)] ?? null,
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

/**
 * SO000001: line 1 split-edited, line 3 a saved draft, line 2 untouched (NOT covered).
 * SO000002: line 1 a saved draft only (no split). Two orders in this Confirm.
 */
function coveredBoard() {
  return withDraft(
    withSplitEdited(boardOf([SO1_L1, SO1_L2, SO1_L3, SO2_L1]), ['pl-1-1']),
    ['pl-1-3', 'pl-2-1'],
    { 'pl-1-3': 'USE BRW 522 & ORDER 294', 'pl-2-1': 'ORDER BACK' },
  );
}

/** Only SO000001's line 1 split-edited: one order in this Confirm, one covered line. */
function oneEditedBoard() {
  return withSplitEdited(boardOf([SO1_L1, SO1_L2, SO2_L1]), ['pl-1-1']);
}

/** A saved draft on SO000001 line 1 only. */
function draftOnlyBoard() {
  return withDraft(boardOf([SO1_L1, SO1_L2]), ['pl-1-1']);
}

type ReadLine = { id: string; no: number; item: string; edited?: boolean };

/** The split read of an order. `edited` lines carry split rows; others are unsplit with `remark`. */
function splitRead(psoId: string, so: string, lines: ReadLine[]) {
  return {
    pso_id: psoId,
    so_number: so,
    so_date: '2026-09-03',
    customer: 'Test Customer',
    project: 'Test Project',
    confirmed_at: null,
    lines: lines.map((l) => ({
      ...wireLine(l.no, l.item, 10, '2026-09-20', {
        line_id: l.id,
        now_qty: 10,
        split_state: l.edited ? 'acting' : 'applied',
        split_view: { status: l.edited ? 'saved' : 'confirmed' },
        splits: l.edited
          ? [wireSplit(`${l.id}-a`, 6, '2026-09-20', l.id), wireSplit(`${l.id}-b`, 4, '2026-10-20', null)]
          : [],
      }),
    })),
  };
}

const SO1_READ = () =>
  splitRead('pso-so-1', 'SO000001', [
    { id: 'pl-1-1', no: 1, item: 'ZZT-ITEM-1', edited: true },
    { id: 'pl-1-2', no: 2, item: 'ZZT-ITEM-1B' },
    { id: 'pl-1-3', no: 3, item: 'ZZT-ITEM-1C' },
  ]);
const SO2_READ = () =>
  splitRead('pso-so-2', 'SO000002', [{ id: 'pl-2-1', no: 1, item: 'ZZT-ITEM-2' }]);

function serveSplits(reads: Record<string, unknown> = {}) {
  getLineSplits.mockImplementation((psoId: string) =>
    Promise.resolve(
      reads[psoId] ?? (psoId === 'pso-so-1' ? SO1_READ() : psoId === 'pso-so-2' ? SO2_READ() : null),
    ),
  );
}

type Row = Record<string, unknown>;

/** The dry run (pressed from the Confirm step): ok for every order unless `error`, rows irrelevant. */
function dryRunAnswers(
  perPso: Record<string, { error?: string; confirmed?: Row[] }> = {},
) {
  previewConfirmMany.mockImplementation((body: { orders: { pso_id: string; lines: { project_line_id: string }[] }[] }) =>
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
          lines_confirmed: spec.confirmed ?? [
            { project_line_id: 'pl-x', line_no: 1, item_code: 'ZZT-ITEM-1' },
          ],
          lines_carried: 0,
          lines_held_back: [],
          lines_fulfilled_skipped: 0,
          inquiry_rows: [],
          transfers: [],
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
const pageOf = (so: string) =>
  screen.getAllByTestId('confirm-guide-split-page').find((el) => el.getAttribute('data-so') === so)!;

beforeEach(() => {
  vi.clearAllMocks();
  serveSplits();
  saveLineSplits.mockImplementation(() => Promise.resolve(SO1_READ()));
  putLineDraft.mockResolvedValue({
    decision: { verdict: 'approved' },
    saved_by: 'Test Planner',
    saved_at: '2026-09-03T00:00:00Z',
  });
  dryRunAnswers();
  confirmAnswers();
});

// ---------------------------------------------------------------------------
// T-FE1: A1, A2, A3, F1
// ---------------------------------------------------------------------------

describe('T-FE1 (A1 A2 A3 F1): Confirm (N) opens the guide and posts nothing', () => {
  it('opens the guide on press, with no dry run and no confirm call yet', async () => {
    await mountWith(oneEditedBoard());
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)');
    await openConfirmGuide();
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
    expect(confirmMany).not.toHaveBeenCalled();
    expect(previewConfirmMany).not.toHaveBeenCalled();
  });

  it('names the orders of this Confirm in the title', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    expect(screen.getByTestId('confirm-guide')).toHaveTextContent('Confirm SO000001, SO000002');
  });

  it('F1: two steps, "Review split" then "Confirm", and no review table, transfers or AutoCount label', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    await screen.findAllByTestId('confirm-guide-split-page');
    const steps = screen.getByTestId('confirm-guide-steps');
    const items = within(steps).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(steps).toHaveTextContent('Review split');
    expect(steps).toHaveTextContent('Confirm');
    expect(screen.queryByTestId('confirm-guide-review')).not.toBeInTheDocument();
    expect(screen.queryByTestId('confirm-guide-review-row')).not.toBeInTheDocument();
    expect(screen.queryByTestId('confirm-guide-autocount')).not.toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide')).not.toHaveTextContent(/transfer/i);
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

  it('Escape and Cancel on the Confirm step still write nothing', async () => {
    await mountWith(draftOnlyBoard(), ['SO000001']);
    await walkToConfirmStep();
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
// T-FE2: F2, F3, F4
// ---------------------------------------------------------------------------

describe('T-FE2 (F2 F3 F4): a page for every order, listing every covered line and only those', () => {
  it('one page per order of this Confirm, in board order, including an order with only a saved draft', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const first = await screen.findByTestId('confirm-guide-split-page');
    expect(first).toHaveAttribute('data-so', 'SO000001');
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(getLineSplits).toHaveBeenCalledWith('pso-so-1');
    expect(getLineSplits).toHaveBeenCalledWith('pso-so-2');
  });

  it('an order not in this Confirm gets no page', async () => {
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await waitFor(() => expect(pages()).toHaveLength(1));
    expect(pages()[0]).toHaveAttribute('data-so', 'SO000001');
    expect(getLineSplits).not.toHaveBeenCalledWith('pso-so-2');
  });

  it('lists exactly the covered lines: the split-edited line with its splits, the drafted unsplit line as one row, never the untouched line', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(await within(page).findByTestId('split-line-1')).toBeInTheDocument();
    expect(within(page).getByTestId('split-line-3')).toBeInTheDocument();
    expect(within(page).queryByTestId('split-line-2')).not.toBeInTheDocument();
    // the split-edited line shows its split rows (6 and 4) as the editable sheet's input values
    expect((qty(1, 1) as HTMLInputElement).value).toBe('6');
    expect((qty(1, 2) as HTMLInputElement).value).toBe('4');
  });

  it('an unsplit covered line is ONE row whose Remark is the board contribution\'s saved_remark', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const line3 = await within(page).findByTestId('split-line-3');
    expect(line3).toHaveTextContent('USE BRW 522 & ORDER 294');
    expect(within(line3).getAllByRole('row')).toHaveLength(1);
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(await within(pageOf('SO000002')).findByTestId('split-line-1')).toHaveTextContent('ORDER BACK');
  });

  it('B2: an order not yet adopted (no split read) still gets its page: the saved draft line as ONE row with its saved_remark', async () => {
    const board = withDraft(boardOf([SO1_L1]), ['pl-1-1'], { 'pl-1-1': 'ORDER' });
    const unadopted = mapContributions(
      { ...board, orders: board.orders.map((o) => ({ ...o, project_sales_order_id: null })) } as unknown as Board,
      (entry) => ({ ...entry, project_line_id: null, project_sales_order_id: null }),
    );
    await mountWith(unadopted, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(page).toHaveAttribute('data-so', 'SO000001');
    expect(await within(page).findByTestId('split-line-1')).toHaveTextContent('ORDER');
    expect(page).not.toHaveTextContent('No split lines');
    expect(page.textContent).toMatch(/1 line(?!s)/);
    expect(getLineSplits).not.toHaveBeenCalled();
  });

  it('B2: a covered book-cancelled line with no draft shows one row with the cancel word', async () => {
    const board = mapContributions(boardOf([SO1_L1, SO1_L2]), (entry) =>
      entry.project_line_id === 'pl-1-2'
        ? { ...entry, cancelled: true, cancelled_at: null, saved_remark: 'CANCEL ALL' }
        : entry,
    );
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(await within(page).findByTestId('split-line-2')).toHaveTextContent('CANCEL ALL');
  });

  it('B2: the header count equals the rows shown', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    const shown = page.querySelectorAll('[data-testid^="split-line-"]').length;
    const count = Number(page.textContent?.match(/(\d+) lines?/)?.[1]);
    expect(count).toBe(shown);
  });

  it('F13 pin: the board gear\'s "Split delivery" is not scoped', async () => {
    await mountWith(coveredBoard());
    const trigger = await screen.findByRole('button', { name: 'Board actions' });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Split delivery SO000001' }));
    const edit = await screen.findByTestId('line-split-dialog');
    expect(edit).toHaveAttribute('data-only-lines', '');
  });

  it('F14: Next is disabled while the page is still reading, enabled once it has loaded', async () => {
    let release: (value: unknown) => void = () => undefined;
    getLineSplits.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    const next = screen.getByTestId('confirm-guide-next') as HTMLButtonElement;
    expect(next).toBeDisabled();
    release(SO1_READ());
    await within(screen.getByTestId('confirm-guide-split-page')).findByTestId('split-line-1');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  });

  it('F15: a saved Reject row shows the email\'s word for the withdrawal, not a blank Remark', async () => {
    const board = withDraft(boardOf([SO1_L1]), ['pl-1-1'], { 'pl-1-1': 'CANCEL ALL' });
    serveSplits({
      'pso-so-1': splitRead('pso-so-1', 'SO000001', [{ id: 'pl-1-1', no: 1, item: 'ZZT-ITEM-1' }]),
    });
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(await within(page).findByTestId('split-line-1')).toHaveTextContent('CANCEL ALL');
  });

  it('F4: the header names the order, the badge, the line count (singular for 1), and no Split delivery button', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(page).toHaveTextContent('SO000001');
    expect(page).toHaveTextContent('Saved, not confirmed');
    expect(page.textContent).toMatch(/2 lines/);
    expect(within(page).queryByTestId('confirm-guide-split-edit')).not.toBeInTheDocument();
    expect(within(page).queryByRole('button', { name: /^Split delivery/ })).not.toBeInTheDocument();
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(pageOf('SO000002').textContent).toMatch(/1 line(?!s)/);
  });

  it('a Confirm with no split edit anywhere still opens at the first order\'s page, two steps', async () => {
    await mountWith(draftOnlyBoard(), ['SO000001']);
    await openConfirmGuide();
    expect(await screen.findByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001');
    expect(within(screen.getByTestId('confirm-guide-steps')).getAllByRole('listitem')).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// T-FE3: F5, B4, F7
// ---------------------------------------------------------------------------

describe('T-FE3 (F5 B4 F7): walking, editing and failing a page', () => {
  it('Next walks the pages one by one, the Confirm step comes only after the last, no dry run yet', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    expect(screen.getByTestId('confirm-guide-next')).toHaveTextContent('Next order');
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    click('confirm-guide-next');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    click('confirm-guide-next');
    expect(await screen.findByTestId('confirm-guide-confirm')).toBeInTheDocument();
    expect(previewConfirmMany).not.toHaveBeenCalled();
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('Back returns to the previous page, and from the Confirm step to the last page', async () => {
    await mountWith(coveredBoard());
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
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-split-page');
    click('confirm-guide-next');
    await screen.findByTestId('confirm-guide-confirm');
    click('confirm-guide-back');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
  });

  it('F7: a read that fails says so with Retry, Next off, and Back and Cancel working', async () => {
    getLineSplits.mockRejectedValue(new Error('boom'));
    await mountWith(oneEditedBoard());
    await openConfirmGuide();
    expect(await screen.findByTestId('confirm-guide-split-error')).toBeInTheDocument();
    const next = screen.queryByTestId('confirm-guide-next') as HTMLButtonElement | null;
    expect(next === null || next.disabled).toBe(true);
    getLineSplits.mockImplementation(() => Promise.resolve(SO1_READ()));
    click('confirm-guide-split-retry');
    await waitFor(() =>
      expect(screen.queryByTestId('confirm-guide-split-error')).not.toBeInTheDocument(),
    );
    expect(await screen.findByTestId('split-line-1')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('F7: Cancel works on a page that failed to load', async () => {
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
// T-FE4: F6 and C7 (the Confirm press runs today's silent dry run, narrowing, post, result card)
// ---------------------------------------------------------------------------

describe('T-FE4 (F6 C7): the Confirm step', () => {
  it('summarises the orders and their lines and offers one button, nothing posted', async () => {
    await mountWith(coveredBoard());
    const confirm = (await walkToConfirmStep())!;
    expect(screen.getByTestId('confirm-guide')).toHaveTextContent(
      '2 orders: SO000001 (2 lines), SO000002 (1 line). Nothing has been sent yet.',
    );
    expect(confirm).toHaveTextContent('Confirm 2 orders');
    expect(previewConfirmMany).not.toHaveBeenCalled();
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('a single order reads "1 order" in the summary and on the button', async () => {
    await mountWith(draftOnlyBoard(), ['SO000001']);
    const confirm = (await walkToConfirmStep())!;
    expect(screen.getByTestId('confirm-guide')).toHaveTextContent(
      '1 order: SO000001 (1 line). Nothing has been sent yet.',
    );
    expect(confirm).toHaveTextContent('Confirm 1 order');
  });

  it('every order refused by the dry run: nothing is posted and today\'s result card shows the reasons', async () => {
    dryRunAnswers({
      'pso-so-1': { error: 'Line 1 has no supply.' },
      'pso-so-2': { error: 'Line 1 is held.' },
    });
    await mountWith(coveredBoard());
    await walkConfirmGuide();
    const card = await screen.findByTestId('board-confirm-results');
    expect(card).toHaveTextContent('Line 1 has no supply.');
    expect(card).toHaveTextContent('Line 1 is held.');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('some orders refused and some ok: only the ok order posts and the card lists the refusal', async () => {
    dryRunAnswers({ 'pso-so-2': { error: 'Line 1 has no supply.' } });
    await mountWith(coveredBoard());
    await walkConfirmGuide();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    expect(body.orders.map((o: { pso_id: string }) => o.pso_id)).toEqual(['pso-so-1']);
    expect(await screen.findByTestId('board-confirm-results')).toHaveTextContent('Line 1 has no supply.');
  });

  it('an order the press drops as having nothing to confirm lands on the result card, nothing posted', async () => {
    dryRunAnswers({ 'pso-so-1': { confirmed: [] } });
    await mountWith(draftOnlyBoard(), ['SO000001']);
    await walkConfirmGuide();
    const card = await screen.findByTestId('board-confirm-results');
    expect(card).toHaveTextContent('has nothing to confirm');
    expect(confirmMany).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// T-FE5: D2, D3 (F6)
// ---------------------------------------------------------------------------

describe('T-FE5 (D2 D3 F6): the Confirm button posts what today\'s press posts', () => {
  it('runs the dry run once from the button, posts its body once, shows the result card and closes the guide', async () => {
    await mountWith(oneEditedBoard());
    await walkConfirmGuide();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    expect(previewConfirmMany).toHaveBeenCalledTimes(1);
    const [dryBody] = previewConfirmMany.mock.calls[0];
    const [body] = confirmMany.mock.calls[0];
    expect(body).not.toHaveProperty('preview');
    expect(body.orders.map((o: { pso_id: string }) => o.pso_id)).toEqual(['pso-so-1']);
    expect(body.orders[0].pso_id).toBe(dryBody.orders[0].pso_id);
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

  it('a failed post toasts the error and leaves the guide open at the Confirm step with the button enabled again', async () => {
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

// ---------------------------------------------------------------------------
// T-FE6: F18 to F21 (round 7, owner hand test 3): split in place on the guide page
// ---------------------------------------------------------------------------

/** SO000001 line 3 only: a saved draft with the email's words, an open unsplit line. */
function oneDraftBoard() {
  return withDraft(boardOf([SO1_L3]), ['pl-1-3'], { 'pl-1-3': 'USE BRW 522 & ORDER 294' });
}
const LINE3_READ = () =>
  splitRead('pso-so-1', 'SO000001', [{ id: 'pl-1-3', no: 3, item: 'ZZT-ITEM-1C' }]);
const LINE3_SPLIT_READ = () => ({
  ...LINE3_READ(),
  lines: [
    wireLine(3, 'ZZT-ITEM-1C', 10, '2026-09-20', {
      line_id: 'pl-1-3',
      now_qty: 10,
      split_state: 'acting',
      split_view: { status: 'saved' },
      splits: [wireSplit('n1', 6, '2026-09-20', 'pl-1-3'), wireSplit('n2', 4, '2026-10-20', null)],
    }),
  ],
});

async function openEditablePage() {
  serveSplits({ 'pso-so-1': LINE3_READ() });
  await mountWith(oneDraftBoard(), ['SO000001']);
  await openConfirmGuide();
  const page = await screen.findByTestId('confirm-guide-split-page');
  await within(page).findByTestId('split-line-3');
  return page;
}

/** One real edit: line 3 split into 6 + 4 (the 4 on a later date). */
async function editLine3() {
  await splitLine(3);
  typeQty(3, 1, '6');
  fireEvent.click(addBtn(3));
  await screen.findByLabelText('Quantity, line 3 split 2');
  typeDate(3, 2, '20/10/2026');
}

describe('T-FE6 (F18 F19 F21): the guide page is the editable split sheet', () => {
  it('F18: the page renders the editable sheet inline: a Split control for the covered open line, no button that opens a dialog', async () => {
    const page = await openEditablePage();
    expect(within(page).getAllByRole('button', { name: /^Split line \d+ quantity$/ }).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('confirm-guide-split-edit')).not.toBeInTheDocument();
    expect(screen.queryByTestId('line-split-dialog')).not.toBeInTheDocument();
    // an unsplit covered line still carries the email's words
    expect(within(page).getByTestId('split-line-3')).toHaveTextContent('USE BRW 522 & ORDER 294');
  });

  it('F18/F22: the page has its own Save; it sends EVERY line of the order, the edited line carries the edit, and the page stays and re-reads', async () => {
    const withHidden = () => {
      const read = LINE3_READ();
      read.lines = [
        ...splitRead('pso-so-1', 'SO000001', [{ id: 'pl-1-2', no: 2, item: 'ZZT-ITEM-1B' }]).lines,
        ...read.lines,
      ];
      return read;
    };
    serveSplits({ 'pso-so-1': withHidden() });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await editLine3();
    serveSplits({ 'pso-so-1': LINE3_SPLIT_READ() });
    saveLineSplits.mockImplementation(() => Promise.resolve(LINE3_SPLIT_READ()));
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const [psoId, body] = saveLineSplits.mock.calls[0];
    expect(psoId).toBe('pso-so-1');
    // F22: the scope limits what is drawn, never what is saved
    expect(body.lines.map((l: { line_id: string }) => l.line_id).sort()).toEqual(['pl-1-2', 'pl-1-3']);
    expect(body.lines.find((l: { line_id: string }) => l.line_id === 'pl-1-3').splits).toHaveLength(2);
    // still on the page, now showing the saved split rows
    expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001');
    await waitFor(() => expect((screen.getByLabelText('Date, line 3 split 2') as HTMLInputElement).value).toBe('20/10/2026'));
    expect(screen.queryByTestId('line-split-dialog')).not.toBeInTheDocument();
  });

  it('F18: a covered line delivered in full is a read-only row', async () => {
    const read = LINE3_READ();
    read.lines = [
      {
        ...wireLine(3, 'ZZT-ITEM-1C', 10, '2026-09-20', {
          line_id: 'pl-1-3',
          delivered_qty: 10,
          now_qty: 0,
          split_state: 'applied',
          split_view: { status: 'confirmed' },
        }),
        delivered_in_full: true,
      } as never,
    ];
    serveSplits({ 'pso-so-1': read });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    expect(within(page).queryByRole('button', { name: /^Split line \d+ quantity$/ })).not.toBeInTheDocument();
    expect(page.querySelectorAll('input')).toHaveLength(0);
  });

  it('F18: every line of an order not yet adopted is a read-only row', async () => {
    const board = withDraft(boardOf([SO1_L1]), ['pl-1-1'], { 'pl-1-1': 'ORDER' });
    const unadopted = mapContributions(
      { ...board, orders: board.orders.map((o) => ({ ...o, project_sales_order_id: null })) } as unknown as Board,
      (entry) => ({ ...entry, project_line_id: null, project_sales_order_id: null }),
    );
    await mountWith(unadopted, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-1');
    expect(within(page).queryByRole('button', { name: /^Split line \d+ quantity$/ })).not.toBeInTheDocument();
    expect(page.querySelectorAll('input')).toHaveLength(0);
  });

  it('F19: with an unsaved edit Next is off and "Save or undo your split changes first" shows; after Save Next is on', async () => {
    const page = await openEditablePage();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
    expect(screen.queryByText('Save or undo your split changes first')).not.toBeInTheDocument();
    await editLine3();
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    expect(screen.getByText('Save or undo your split changes first')).toBeInTheDocument();
    serveSplits({ 'pso-so-1': LINE3_SPLIT_READ() });
    saveLineSplits.mockImplementation(() => Promise.resolve(LINE3_SPLIT_READ()));
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    expect(screen.queryByText('Save or undo your split changes first')).not.toBeInTheDocument();
  });

  it('F19: a failed Save shows the error and keeps the edit, Next stays off', async () => {
    const page = await openEditablePage();
    await editLine3();
    saveLineSplits.mockRejectedValue(new Error('Splits refused'));
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect((qty(3, 1) as HTMLInputElement).value).toBe('6');
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    expect(screen.getByText('Save or undo your split changes first')).toBeInTheDocument();
  });

  it('F21: no line number shows on the guide sheet: no Line column, no "line N" sub-label', async () => {
    const page = await openEditablePage();
    expect(within(page).queryByRole('columnheader', { name: /^line$/i })).not.toBeInTheDocument();
    expect(page.textContent).not.toMatch(/\bline \d+\b/i);
    // identity stays internal: the block is still addressable
    expect(within(page).getByTestId('split-line-3')).toBeInTheDocument();
  });

  it('F24: the problems bar names the item and the qty left, never a line number', async () => {
    const page = await openEditablePage();
    await splitLine(3);
    typeQty(3, 1, '6'); // 4 of 10 left
    await waitFor(() => expect(page.textContent).toMatch(/ZZT-ITEM-1C: 4 left/));
    expect(page.textContent).not.toMatch(/\bline \d+\b/i);
  });

  it('F23: Escape never closes the guide while the page has unsaved edits, Cancel does and posts nothing', async () => {
    const page = await openEditablePage();
    await editLine3();
    fireEvent.keyDown(screen.getByTestId('confirm-guide'), { key: 'Escape' });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
    expect(screen.getByText('Save or undo your split changes first')).toBeInTheDocument();
    expect(within(page).getByLabelText('Quantity, line 3 split 1')).toBeInTheDocument();
    click('confirm-guide-cancel');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    expect(saveLineSplits).not.toHaveBeenCalled();
    expect(confirmMany).not.toHaveBeenCalled();
    expect(previewConfirmMany).not.toHaveBeenCalled();
  });

  it('F23: Escape during a keyboard drag does not close the guide', async () => {
    await openEditablePage();
    const grip = screen.getByRole('button', { name: /^Drag line \d+$/ });
    act(() => grip.focus());
    fireEvent.keyDown(grip, { key: ' ', code: 'Space' });
    await screen.findByTestId('drop-cancel');
    fireEvent.keyDown(document.activeElement ?? grip, { key: 'Escape', code: 'Escape' });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId('confirm-guide')).toBeInTheDocument();
  });

  it('F25: an unsplit saved line\'s Remark is a text box whose VALUE is the email\'s words', async () => {
    await openEditablePage();
    expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('USE BRW 522 & ORDER 294');
  });

  it('F25: editing it shows an "edited" marker; clearing restores the default value and removes the marker', async () => {
    const page = await openEditablePage();
    const box = screen.getByLabelText('Remark, line 3') as HTMLInputElement;
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
    fireEvent.change(box, { target: { value: 'ORDER BACK URGENT' } });
    expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('ORDER BACK URGENT');
    expect(within(page).getByText('edited')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: '' } });
    await waitFor(() =>
      expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('USE BRW 522 & ORDER 294'),
    );
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
  });

  it('F25/F26: saving an edited remark on an unsplit saved line writes the draft decision remark and adds NO split row', async () => {
    const board = oneDraftBoard();
    const key = (board.contributions as unknown as { key: string; project_line_id: string }[]).find(
      (c) => c.project_line_id === 'pl-1-3',
    )!.key;
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'ORDER BACK URGENT' } });
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalled());
    const [draftKey, decision] = putLineDraft.mock.calls[0];
    expect(draftKey).toBe(key);
    expect(decision.remark).toBe('ORDER BACK URGENT');
    // a remark on an unsplit row never becomes a one-row split
    for (const [, body] of saveLineSplits.mock.calls) {
      for (const l of body.lines) {
        if (l.line_id === 'pl-1-3') expect(l.splits).toHaveLength(0);
      }
    }
  });

  it('F25: saving an untouched default sends no remark: the split body carries empty remarks, no draft remark', async () => {
    const page = await openEditablePage();
    await editLine3();
    saveLineSplits.mockImplementation(() => Promise.resolve(LINE3_SPLIT_READ()));
    serveSplits({ 'pso-so-1': LINE3_SPLIT_READ() });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const l3 = saveLineSplits.mock.calls[0][1].lines.find((l: { line_id: string }) => l.line_id === 'pl-1-3');
    expect(l3.splits.map((s: { remark: string }) => s.remark ?? '')).toEqual(['', '']);
    for (const [, decision] of putLineDraft.mock.calls) expect(decision.remark ?? '').toBe('');
  });

  it('F28: a covered line delivered in full has a read-only Remark and says nothing goes to purchasing', async () => {
    const read = LINE3_READ();
    read.lines = [
      {
        ...wireLine(3, 'ZZT-ITEM-1C', 10, '2026-09-20', {
          line_id: 'pl-1-3',
          delivered_qty: 10,
          now_qty: 0,
          split_state: 'applied',
          split_view: { status: 'confirmed' },
        }),
        delivered_in_full: true,
      } as never,
    ];
    serveSplits({ 'pso-so-1': read });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    expect(block).toHaveTextContent('Delivered in full: nothing goes to purchasing');
    expect(block.querySelectorAll('input')).toHaveLength(0);
  });

  /** The board after a draft remark was saved: the contribution carries the stored words. */
  function boardWithStoredRemark(remark: string | null) {
    return mapContributions(oneDraftBoard(), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? {
            ...entry,
            // the backend's saved_remark is always the email's default words; a stored override
            // lives only in the draft decision's `remark`
            saved_remark: 'USE BRW 522 & ORDER 294',
            draft: {
              decision: { verdict: 'approved', ...(remark ? { remark } : {}) },
              saved_by: 'Test Planner',
              saved_at: '2026-09-08T00:00:00Z',
            },
          }
        : entry,
    );
  }

  it('R9d-1: a remark-only Save sends the draft PUT, toasts success and never leaves the page on a skeleton', async () => {
    // Only the FIRST split read ever answers: a remark-only save changes the draft, not the
    // splits, so the page must not wait for a split re-read that never comes.
    getLineSplits
      .mockReset()
      .mockImplementationOnce(() => Promise.resolve(LINE3_READ()))
      .mockImplementation(() => new Promise(() => undefined));
    putLineDraft.mockImplementation(() => {
      getPlanningBoard.mockResolvedValue(boardWithStoredRemark('URGENT ORDER'));
      return Promise.resolve({ decision: { verdict: 'approved', remark: 'URGENT ORDER' }, saved_by: 'Test Planner', saved_at: '2026-09-09T00:00:00Z' });
    });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'URGENT ORDER' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    // the row is still there (no skeleton) with the stored remark and the edited marker
    await waitFor(() => expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('URGENT ORDER'));
    expect(within(screen.getByTestId('confirm-guide-split-page')).getByText('edited')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('R9d-1: saving the default back (clearing the stored remark) also leaves no skeleton', async () => {
    getPlanningBoard.mockResolvedValue(boardWithStoredRemark('URGENT ORDER'));
    getLineSplits
      .mockReset()
      .mockImplementationOnce(() => Promise.resolve(LINE3_READ()))
      .mockImplementation(() => new Promise(() => undefined));
    putLineDraft.mockImplementation(() => {
      getPlanningBoard.mockResolvedValue(boardWithStoredRemark(null));
      return Promise.resolve({ decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-09-09T00:00:00Z' });
    });
    renderPanel(['SO000001']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('URGENT ORDER');
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'USE BRW 522 & ORDER 294' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('USE BRW 522 & ORDER 294'),
    );
    expect(within(screen.getByTestId('confirm-guide-split-page')).queryByText('edited')).not.toBeInTheDocument();
  });

  it('R9d-2: a real focus-out (Tab, and a click elsewhere) on an emptied remark box brings the default back and removes the marker', async () => {
    const user = userEvent.setup();
    const page = await openEditablePage();
    const box = () => screen.getByLabelText('Remark, line 3') as HTMLInputElement;
    await user.click(box());
    await user.clear(box());
    await user.type(box(), 'x');
    expect(within(page).getByText('edited')).toBeInTheDocument();
    await user.clear(box());
    expect(box().value).toBe('');
    await user.tab();
    await waitFor(() => expect(box().value).toBe('USE BRW 522 & ORDER 294'));
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
    // and by clicking another element
    await user.click(box());
    await user.clear(box());
    await user.click(screen.getByTestId('confirm-guide-steps'));
    await waitFor(() => expect(box().value).toBe('USE BRW 522 & ORDER 294'));
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
    // nothing changed against the stored plan, so Next is on and no draft write happens
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
    expect(putLineDraft).not.toHaveBeenCalled();
  });

  it('R9d-3: a saved draft on a line AutoCount added has an editable Remark with the email words; edit + Save writes the draft remark', async () => {
    const added = demand({ project_line_id: 'pl-1-5', line_no: 5, item_code: 'ZZT-ITEM-5' });
    const board = withDraft(boardOf([added]), ['pl-1-5'], { 'pl-1-5': 'ORDER' });
    const key = (board.contributions as unknown as { key: string; project_line_id: string }[]).find(
      (c) => c.project_line_id === 'pl-1-5',
    )!.key;
    const read = splitRead('pso-so-1', 'SO000001', []);
    read.lines = [
      wireLine(5, 'ZZT-ITEM-5', 0, null, {
        line_id: 'pl-1-5',
        now_qty: 4,
        now_date: '2026-10-16',
        pending_change: true,
        new_qty: 4,
        new_date: '2026-10-16',
        split_state: 'applied',
      }),
    ];
    serveSplits({ 'pso-so-1': read });
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-5');
    const box = screen.getByLabelText('Remark, line 5') as HTMLInputElement;
    expect(box.value).toBe('ORDER');
    fireEvent.change(box, { target: { value: 'ORDER 4 FIRST' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalled());
    const [draftKey, decision] = putLineDraft.mock.calls[0];
    expect(draftKey).toBe(key);
    expect(decision.remark).toBe('ORDER 4 FIRST');
  });

  it('R9d-4: clearing a STORED remark and blurring restores the default words and drops the marker; Save then removes the stored remark', async () => {
    const user = userEvent.setup();
    getPlanningBoard.mockResolvedValue(boardWithStoredRemark('URGENT ORDER'));
    serveSplits({ 'pso-so-1': LINE3_READ() });
    putLineDraft.mockImplementation(() => {
      getPlanningBoard.mockResolvedValue(boardWithStoredRemark(null));
      return Promise.resolve({ decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-09-09T00:00:00Z' });
    });
    renderPanel(['SO000001']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    const box = () => screen.getByLabelText('Remark, line 3') as HTMLInputElement;
    expect(box().value).toBe('URGENT ORDER');
    expect(within(page).getByText('edited')).toBeInTheDocument();
    await user.click(box());
    await user.clear(box());
    expect(box().value).toBe('');
    await user.tab();
    await waitFor(() => expect(box().value).toBe('USE BRW 522 & ORDER 294'));
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
    // Save stores nothing: the draft remark is removed
    await user.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalledTimes(1));
    const [, decision] = putLineDraft.mock.calls[0];
    expect(decision.remark ?? '').toBe('');
    await waitFor(() => expect(box().value).toBe('USE BRW 522 & ORDER 294'));
    expect(within(screen.getByTestId('confirm-guide-split-page')).queryByText('edited')).not.toBeInTheDocument();
  });
});
