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
import { openConfirmGuide, walkConfirmGuide, walkToConfirmStep } from '@/test-mocks/confirmGuide';
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
    // the split-edited line shows its split rows (6 and 4), read-only
    expect(within(page).getByTestId('split-line-1')).toHaveTextContent('6');
    expect(within(page).getByTestId('split-line-1')).toHaveTextContent('4');
    expect(page.querySelectorAll('input, [data-drag-handle]')).toHaveLength(0);
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

  it('F4: the header names the order, the badge, the line count (singular for 1) and one CTA', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(page).toHaveTextContent('SO000001');
    expect(page).toHaveTextContent('Saved, not confirmed');
    expect(page.textContent).toMatch(/2 lines/);
    expect(within(page).getByTestId('confirm-guide-split-edit')).toHaveTextContent('Split delivery SO000001');
    expect(within(page).getAllByRole('button', { name: /^Split delivery/ })).toHaveLength(1);
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

  it('after Save the page re-reads and shows the changed values', async () => {
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
            splits: [wireSplit('x1', 3, '2026-09-20', 'pl-1-1'), wireSplit('x2', 7, '2026-12-21', null)],
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
