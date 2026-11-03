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
const adoptSalesOrder = vi.fn();
const confirmSupply = vi.fn();
const confirmMany = vi.fn();
const previewConfirmMany = vi.fn();
const putLineDraft = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: (...args: unknown[]) => adoptSalesOrder(...args),
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
import { MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE } from '../../_shared/__mocks__/planningChanges';
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
  perPso: Record<string, { error?: string; confirmed?: Row[]; email?: Row[] }> = {},
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
          ...(spec.email ? { email_lines: spec.email } : {}),
        };
      }),
    }),
  );
}

/** The press's own dry runs: every preview call but the guide's quiet email ones (round 3). */
function pressDryRuns() {
  return previewConfirmMany.mock.calls.filter(([body]) => !(body as { quiet?: boolean }).quiet);
}
/** The guide's quiet email dry runs (round 3). */
function emailDryRuns() {
  return previewConfirmMany.mock.calls.filter(([body]) => Boolean((body as { quiet?: boolean }).quiet));
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

/** The mounted panel's query client: a test can re-read the board as a save elsewhere would. */
let lastClient: QueryClient | null = null;

function renderPanel(soNumbers: string[] = ['SO000001', 'SO000002']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  lastClient = client;
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
/**
 * Next waits for the fresh board re-read and the order's email dry run (#2091, #2116); a press
 * while it is still off is a no-op, which a loaded CI runner hits (run 41565786700). Wait for it.
 */
async function clickNext() {
  await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  click('confirm-guide-next');
}
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
    // CONFIRM-PREVIEW-STALE round 3: only the guide's own quiet email dry run may have run;
    // walking runs no press (no press dry run, no post) until the guide's Confirm button.
    expect(confirmMany).not.toHaveBeenCalled();
    expect(pressDryRuns()).toHaveLength(0);
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
    // CONFIRM-PREVIEW-STALE round 3: only the guide's own quiet email dry run may have run;
    // walking runs no press (no press dry run, no post) until the guide's Confirm button.
    expect(confirmMany).not.toHaveBeenCalled();
    expect(pressDryRuns()).toHaveLength(0);
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
    await clickNext();
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
    await clickNext();
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

  // PLAN-BATCH-COUNT-DISPLAY (owner ruling 21 Oct 2026 ~16:15): a line the book cancelled is not a
  // decision, so the guide's pages (the lines Confirm (N) counts) leave it out; the board's
  // AutoCount change note names it instead.
  it('B2: a covered book-cancelled line with no draft is not a guide row; it is the AutoCount note', async () => {
    const board = mapContributions(boardOf([SO1_L1, SO1_L2]), (entry) =>
      entry.project_line_id === 'pl-1-2'
        ? { ...entry, cancelled: true, cancelled_at: null, saved_remark: 'CANCEL ALL' }
        : entry,
    );
    await mountWith(board, ['SO000001']);
    expect(await screen.findByTestId('board-autocount-change-note')).toHaveTextContent(
      '1 old line',
    );
    // Nothing else is decided, so the button applies the change and the guide has no line page.
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Apply AutoCount change');
    await openConfirmGuide();
    expect(screen.queryByTestId('split-line-2')).toBeNull();
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
    await clickNext();
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
    await clickNext();
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    expect(screen.queryByTestId('confirm-guide-confirm')).not.toBeInTheDocument();
    // CONFIRM-REMARK-FIX: each page dry-runs its own order; Next waits for this page's words.
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    await clickNext();
    expect(await screen.findByTestId('confirm-guide-confirm')).toBeInTheDocument();
    // CONFIRM-PREVIEW-STALE round 3: only the guide's own quiet email dry run may have run;
    // walking runs no press (no press dry run, no post) until the guide's Confirm button.
    expect(confirmMany).not.toHaveBeenCalled();
    expect(pressDryRuns()).toHaveLength(0);
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('Back returns to the previous page, and from the Confirm step to the last page', async () => {
    await mountWith(coveredBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    await clickNext();
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    click('confirm-guide-back');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001'),
    );
    await clickNext();
    await screen.findByTestId('confirm-guide-split-page');
    await clickNext();
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
    // CONFIRM-PREVIEW-STALE round 3: only the guide's own quiet email dry run may have run;
    // walking runs no press (no press dry run, no post) until the guide's Confirm button.
    expect(confirmMany).not.toHaveBeenCalled();
    expect(pressDryRuns()).toHaveLength(0);
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
    // One press dry run per press (the guide's quiet email dry runs are not the press's).
    expect(pressDryRuns()).toHaveLength(1);
    const [dryBody] = pressDryRuns()[0];
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
    expect(page.querySelectorAll('input:not([data-testid="confirm-guide-so-remark"])')).toHaveLength(0);
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
    expect(page.querySelectorAll('input:not([data-testid="confirm-guide-so-remark"])')).toHaveLength(0);
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
    // CONFIRM-PREVIEW-STALE round 3: only the guide's own quiet email dry run may have run;
    // walking runs no press (no press dry run, no post) until the guide's Confirm button.
    expect(confirmMany).not.toHaveBeenCalled();
    expect(pressDryRuns()).toHaveLength(0);
  });

  it('F23 (OI-SPLIT-CONFIRM-POLISH): the page has no drag, so Space on a row picks nothing up', async () => {
    const page = await openEditablePage();
    expect(within(page).queryByRole('button', { name: /^Drag / })).not.toBeInTheDocument();
    const cell = within(page).getByRole('button', { name: /^Split line 3 quantity$/ });
    act(() => cell.focus());
    fireEvent.keyDown(cell, { key: ' ', code: 'Space' });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId('drop-cancel')).not.toBeInTheDocument();
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

  // CONFIRM-PREVIEW-STALE item 4 (crew ruling 2 Nov; owner rulings 14 Sep, 22 Sep, 12 Oct,
  // 1 Nov): Confirm plans a delivered line at its ordered qty, so its saved decision DOES reach
  // purchasing. The row prints that decision's words, read-only; no "nothing goes" note.
  it('F28 (reworked): a covered line delivered in full prints its saved words read-only, no "nothing goes" note', async () => {
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
    expect(block).not.toHaveTextContent('nothing goes to purchasing');
    expect(block).toHaveTextContent('USE BRW 522 & ORDER 294');
    expect(block.querySelectorAll('input')).toHaveLength(0);
  });

  // CONFIRM-ITEM4 (crew, #2122 check, 3 Nov): the note must never contradict what the Confirm
  // sends. The guide's email dry run is the truth: the note reads only when the dry run
  // previewed the order and the email holds no line for the delivered line.
  const DELIVERED_LINE3_READ = () => {
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
    return read;
  };

  it('CONFIRM-ITEM4: a delivered line the email tells (ORDER BACK) never says nothing goes to purchasing', async () => {
    serveSplits({ 'pso-so-1': DELIVERED_LINE3_READ() });
    dryRunAnswers({ 'pso-so-1': { email: [{ so_line_id: 'pl-1-3', remark: 'ORDER BACK 10' }] } });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(emailDryRuns().length).toBeGreaterThan(0));
    await waitFor(() => expect(block).toHaveTextContent('ORDER BACK 10'));
    expect(block).not.toHaveTextContent('nothing goes to purchasing');
  });

  it('CONFIRM-ITEM4: a delivered line the email holds no line for keeps the note (it is true)', async () => {
    serveSplits({ 'pso-so-1': DELIVERED_LINE3_READ() });
    dryRunAnswers({ 'pso-so-1': { email: [] } });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(emailDryRuns().length).toBeGreaterThan(0));
    await waitFor(() =>
      expect(block).toHaveTextContent('Delivered in full: nothing goes to purchasing'),
    );
  });

  it('CONFIRM-ITEM4: a delivered line on a failed email dry run makes no claim either way', async () => {
    serveSplits({ 'pso-so-1': DELIVERED_LINE3_READ() });
    dryRunAnswers({ 'pso-so-1': { error: 'boom' } });
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(emailDryRuns().length).toBeGreaterThan(0));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(block).not.toHaveTextContent('nothing goes to purchasing');
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

  it('F32: a covered CONFIRMED line whose board data carries the confirmed remark shows it with the "edited" marker, and the re-approve body carries it', async () => {
    const board = mapContributions(oneDraftBoard(), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? { ...entry, confirmed_remark: 'URGENT ORDER', saved_remark: 'USE BRW 522 & ORDER 294' }
        : entry,
    );
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('URGENT ORDER');
    expect(within(page).getByText('edited')).toBeInTheDocument();
    await clickNext();
    await screen.findByTestId('confirm-guide-confirm');
    click('confirm-guide-confirm');
    await waitFor(() => expect(pressDryRuns()).toHaveLength(1));
    const [body] = pressDryRuns()[0];
    const line = body.orders[0].lines.find((l: { project_line_id: string }) => l.project_line_id === 'pl-1-3');
    expect(line, JSON.stringify(body)).toBeDefined();
    expect(line.remark).toBe('URGENT ORDER');
  });
});

describe('OI-SPLIT-GEAR-REMARK guide Review page: confirmed remark vs the server words', () => {
  const withRemarks = (board: Board, lineId: string, extra: Record<string, unknown>) =>
    mapContributions(board, (entry) => (entry.project_line_id === lineId ? { ...entry, ...extra } : entry));
  const REJECT = { verdict: 'rejected' };

  async function reviewLine1(board: Board, generated = '') {
    const read = splitRead('pso-so-1', 'SO000001', [{ id: 'pl-1-1', no: 1, item: 'ZZT-ITEM-1' }]);
    read.lines = read.lines.map((l) => ({ ...l, remark_generated: generated }));
    serveSplits({ 'pso-so-1': read });
    await mountWith(board, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-1');
    return page;
  }

  it('H5: a covered no-draft line (split-edited) with a confirmed remark X shows X on the Review page', async () => {
    const board = withRemarks(withSplitEdited(boardOf([SO1_L1]), ['pl-1-1']), 'pl-1-1', { confirmed_remark: 'URGENT ORDER' });
    const page = await reviewLine1(board);
    expect((screen.getByLabelText('Remark, line 1') as HTMLInputElement).value).toBe('URGENT ORDER');
    expect(within(page).getByText('edited')).toBeInTheDocument();
  });

  it('H10: a reserve-only Reject draft (no server words) never shows the confirmed remark in the editor', async () => {
    const board = withRemarks(boardOf([SO1_L1]), 'pl-1-1', {
      saved_remark: null,
      confirmed_remark: 'URGENT ORDER',
      draft: { decision: REJECT, saved_by: 'Test Planner', saved_at: '2026-09-08T00:00:00Z' },
    });
    const page = await reviewLine1(board, 'DEFAULT WORDS');
    expect((screen.getByLabelText('Remark, line 1') as HTMLInputElement).value).toBe('DEFAULT WORDS');
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
  });

  it('H10: an order not yet adopted (read-only row) with a Reject draft shows the server words, never X', async () => {
    const board = withRemarks(boardOf([SO1_L1]), 'pl-1-1', {
      saved_remark: 'CANCEL ALL',
      confirmed_remark: 'URGENT ORDER',
      draft: { decision: REJECT, saved_by: 'Test Planner', saved_at: '2026-09-08T00:00:00Z' },
    });
    const unadopted = mapContributions(
      { ...board, orders: board.orders.map((o) => ({ ...o, project_sales_order_id: null })) } as unknown as Board,
      (entry) => ({ ...entry, project_line_id: null, project_sales_order_id: null }),
    );
    await mountWith(unadopted, ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const row = await within(page).findByTestId('split-line-1');
    expect(within(row).getByText('CANCEL ALL')).toBeInTheDocument();
    expect(within(row).queryByText('URGENT ORDER')).not.toBeInTheDocument();
  });

  it('H7: a saved Reject draft line with saved_remark "CANCEL ALL" and confirmed X shows CANCEL ALL, no marker', async () => {
    const board = withRemarks(boardOf([SO1_L1]), 'pl-1-1', {
      saved_remark: 'CANCEL ALL',
      confirmed_remark: 'URGENT ORDER',
      draft: { decision: REJECT, saved_by: 'Test Planner', saved_at: '2026-09-08T00:00:00Z' },
    });
    const page = await reviewLine1(board, 'CANCEL ALL');
    expect((screen.getByLabelText('Remark, line 1') as HTMLInputElement).value).toBe('CANCEL ALL');
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
  });

  it('H7: a book-cancelled no-draft line with saved_remark "CANCEL ALL" and confirmed X shows CANCEL ALL, no marker', async () => {
    const board = withRemarks(withSplitEdited(boardOf([SO1_L1]), ['pl-1-1']), 'pl-1-1', {
      saved_remark: 'CANCEL ALL',
      confirmed_remark: 'URGENT ORDER',
    });
    const page = await reviewLine1(board, 'CANCEL ALL');
    expect((screen.getByLabelText('Remark, line 1') as HTMLInputElement).value).toBe('CANCEL ALL');
    expect(within(page).queryByText('edited')).not.toBeInTheDocument();
  });
});

/*
 * OI-SPLIT-CONFIRM-POLISH (owner, 21 Oct 2026), on an order shaped like SO426513: two C-FH14
 * lines at BRW-ED, both saved decisions, not confirmed. Line 1 (40) has 20 moved onto line 2's
 * date (19/10/2026), the case the owner's screenshots showed.
 */
/*
 * Owner, SO426939 (21 Oct ~23:25): three saved lines on an order nobody has adopted yet open
 * Review split as the READ-ONLY sheet (no split read, no Undo/Save), and SO DATE was blank on
 * every row. The board's order carries the SO date; every sheet on the page prints it.
 */
describe('OI-SPLIT-CONFIRM-POLISH: an order nobody adopted opens Review split editable (SO426939)', () => {
  const RO = (no: number, item: string) =>
    demand({
      sales_order_id: 'so-9',
      so_number: 'SO426939',
      project_sales_order_id: null,
      project_line_id: `pl-9-${no}`,
      line_no: no,
      item_code: item,
      fulfilment_location: 'BRW-BB',
      qty: '1115',
      required_date: '2030-01-01',
    });
  const RO_LINES = [RO(1, 'SRTWC8613-RL'), RO(2, 'SRTWT907SS'), RO(3, 'WESERP10B')];
  const firstCells = (page: HTMLElement) =>
    Array.from(page.querySelectorAll('tbody[data-line-id]')).map((body) => body.querySelector('td')?.textContent ?? '');

  /** SO426939 as the board states it: saved decisions on all three lines. */
  function soBoard(adopted: boolean, soDate: string | null = '2026-10-20') {
    const board = withDraft(boardOf(RO_LINES), ['pl-9-1', 'pl-9-2', 'pl-9-3'], { 'pl-9-1': 'ORDER' });
    if (adopted) {
      return {
        ...board,
        orders: board.orders.map((o) => ({ ...o, project_sales_order_id: 'pso-so-9', so_date: soDate })),
      } as unknown as Board;
    }
    return mapContributions(
      {
        ...board,
        orders: board.orders.map((o) => ({ ...o, project_sales_order_id: null, so_date: soDate })),
      } as unknown as Board,
      (entry) => ({ ...entry, project_line_id: null, project_sales_order_id: null }),
    );
  }
  const SO9_READ = () => ({
    ...splitRead('pso-so-9', 'SO426939', []),
    so_date: '2026-10-20',
    lines: [
      wireLine(1, 'SRTWC8613-RL', 1115, '2030-01-01', { line_id: 'pl-9-1', location: 'BRW-BB', split_view: { status: 'saved' } }),
      wireLine(2, 'SRTWT907SS', 1115, '2030-01-01', { line_id: 'pl-9-2', location: 'BRW-BB', split_view: { status: 'saved' } }),
      wireLine(3, 'WESERP10B', 1115, '2030-01-01', { line_id: 'pl-9-3', location: 'BRW-BB', split_view: { status: 'saved' } }),
    ],
  });

  /** The board reads unadopted until the guide's adopt lands, adopted after it. */
  function serveAdoption() {
    let adopted = false;
    adoptSalesOrder.mockImplementation(async () => {
      adopted = true;
      return { project_sales_order_id: 'pso-so-9', so_number: 'SO426939', review_state: 'in_review', already_adopted: false };
    });
    getPlanningBoard.mockImplementation(async () => soBoard(adopted));
    serveSplits({ 'pso-so-9': SO9_READ() });
  }

  it('first open: the guide gives the order its planning record, then shows the EDITABLE sheet with + Split', async () => {
    serveAdoption();
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByRole('button', { name: 'Undo' });
    expect(adoptSalesOrder).toHaveBeenCalledTimes(1);
    expect(adoptSalesOrder).toHaveBeenCalledWith('so-9');
    expect(within(page).getAllByRole('button', { name: /^Split line \d+ quantity$/ })).toHaveLength(3);
    expect(within(page).getAllByRole('button', { name: /^Add a split to line \d+$/ })).toHaveLength(3);
    expect(firstCells(page)).toEqual(['20/10/2026', '20/10/2026', '20/10/2026']);
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('never shows the read-only sheet while the order is being made ready: a skeleton, Next off', async () => {
    let finish: (value: unknown) => void = () => undefined;
    adoptSalesOrder.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    getPlanningBoard.mockImplementation(async () => soBoard(false));
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(within(page).queryByRole('table', { name: 'Split delivery sheet' })).not.toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    await act(async () => {
      finish({ project_sales_order_id: 'pso-so-9', so_number: 'SO426939', review_state: 'in_review', already_adopted: false });
    });
  });

  it('a failed adopt says so with a Retry above the order\'s lines, Next stays on, and Retry gets the editable sheet', async () => {
    let adopted = false;
    adoptSalesOrder.mockRejectedValueOnce(new Error('Could not start planning SO426939'));
    getPlanningBoard.mockImplementation(async () => soBoard(adopted));
    serveSplits({ 'pso-so-9': SO9_READ() });
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    expect(await within(page).findByRole('alert')).toHaveTextContent('Could not start planning SO426939');
    // the order's lines stay listed (what the Confirm covers), and one order that cannot be
    // planned never holds up the rest of the Confirm: the press names it in its results
    expect(firstCells(page)).toEqual(['20/10/2026', '20/10/2026', '20/10/2026']);
    expect(within(page).queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
    adoptSalesOrder.mockImplementation(async () => {
      adopted = true;
      return { project_sales_order_id: 'pso-so-9', so_number: 'SO426939', review_state: 'in_review', already_adopted: false };
    });
    fireEvent.click(within(page).getByRole('button', { name: 'Retry' }));
    await within(page).findByRole('button', { name: 'Undo' });
    expect(within(page).getAllByRole('button', { name: /^Add a split to line \d+$/ })).toHaveLength(3);
  });

  it('phone header (375): the page header shows the same SO date, DD/MM/YYYY, phone-only', async () => {
    serveAdoption();
    window.innerWidth = 375;
    window.dispatchEvent(new Event('resize'));
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByRole('button', { name: 'Undo' });
    const header = within(page).getByTestId('confirm-guide-so-date');
    expect(header).toHaveTextContent(/^20\/10\/2026$/);
    // phone-only: the desktop sheet already has its SO DATE column
    expect(header).toHaveClass('md:hidden');
    // the same value the sheet's SO DATE cells print
    expect(firstCells(page)).toEqual(['20/10/2026', '20/10/2026', '20/10/2026']);
    window.innerWidth = 1024;
  });

  it('phone header: no SO date anywhere, no header date', async () => {
    getPlanningBoard.mockImplementation(async () => soBoard(true, null));
    serveSplits({ 'pso-so-9': { ...SO9_READ(), so_date: null } });
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByRole('button', { name: 'Undo' });
    expect(within(page).queryByTestId('confirm-guide-so-date')).not.toBeInTheDocument();
  });

  it('two orders, one adopt fails: the adopted order is editable, the other shows ITS OWN error', async () => {
    const ok = (no: number, item: string) =>
      demand({
        sales_order_id: 'so-8',
        so_number: 'SO426800',
        project_sales_order_id: null,
        project_line_id: `pl-8-${no}`,
        line_no: no,
        item_code: item,
        fulfilment_location: 'BRW-BB',
        qty: '10',
        required_date: '2030-01-01',
      });
    const adoptedIds = new Set<string>();
    const twoBoard = () => {
      const board = withDraft(boardOf([ok(1, 'ZZT-OK-1'), ...RO_LINES]), ['pl-8-1', 'pl-9-1', 'pl-9-2', 'pl-9-3']);
      return mapContributions(
        {
          ...board,
          orders: board.orders.map((o) => ({
            ...o,
            project_sales_order_id: adoptedIds.has(o.sales_order_id) ? `pso-${o.sales_order_id}` : null,
            so_date: '2026-10-20',
          })),
        } as unknown as Board,
        (entry) =>
          adoptedIds.has(String(entry.sales_order_id))
            ? { ...entry, project_sales_order_id: `pso-${entry.sales_order_id}` }
            : { ...entry, project_line_id: null, project_sales_order_id: null },
      );
    };
    adoptSalesOrder.mockImplementation(async (salesOrderId: string) => {
      if (salesOrderId === 'so-9') throw new Error('Another planning record already holds SO426939.');
      adoptedIds.add(salesOrderId);
      return { project_sales_order_id: `pso-${salesOrderId}`, so_number: 'SO426800', review_state: 'in_review', already_adopted: false };
    });
    getPlanningBoard.mockImplementation(async () => twoBoard());
    serveSplits({
      'pso-so-8': {
        ...splitRead('pso-so-8', 'SO426800', []),
        so_date: '2026-10-20',
        lines: [wireLine(1, 'ZZT-OK-1', 10, '2030-01-01', { line_id: 'pl-8-1', location: 'BRW-BB', split_view: { status: 'saved' } })],
      },
    });
    renderPanel(['SO426800', 'SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const first = await screen.findByTestId('confirm-guide-split-page');
    expect(first).toHaveAttribute('data-so', 'SO426800');
    await within(first).findByRole('button', { name: 'Undo' });
    expect(within(first).getAllByRole('button', { name: /^Add a split to line \d+$/ })).toHaveLength(1);
    expect(within(first).queryByRole('alert')).not.toBeInTheDocument();
    expect(adoptSalesOrder).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByTestId('confirm-guide-next'));
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO426939'),
    );
    const second = screen.getByTestId('confirm-guide-split-page');
    expect(within(second).getByRole('alert')).toHaveTextContent('Another planning record already holds SO426939.');
  });

  it('the adopt\'s own planning record wins when the board re-read still reports none', async () => {
    adoptSalesOrder.mockResolvedValue({
      project_sales_order_id: 'pso-so-9',
      so_number: 'SO426939',
      review_state: 'in_review',
      already_adopted: false,
    });
    // the re-read names the mirror lines but, as for SO419851, not the record itself
    const stillNull = () => {
      const board = soBoard(true);
      return { ...board, orders: board.orders.map((o) => ({ ...o, project_sales_order_id: null })) } as unknown as Board;
    };
    getPlanningBoard.mockResolvedValueOnce(soBoard(false)).mockImplementation(async () => stillNull());
    serveSplits({ 'pso-so-9': SO9_READ() });
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByRole('button', { name: 'Undo' });
    expect(getLineSplits).toHaveBeenCalledWith('pso-so-9');
    expect(within(page).getAllByRole('button', { name: /^Add a split to line \d+$/ })).toHaveLength(3);
  });

  it('an order that already has its planning record is not adopted again', async () => {
    getPlanningBoard.mockImplementation(async () => soBoard(true));
    serveSplits({ 'pso-so-9': SO9_READ() });
    renderPanel(['SO426939']);
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByRole('button', { name: 'Undo' });
    expect(adoptSalesOrder).not.toHaveBeenCalled();
    expect(firstCells(page)).toEqual(['20/10/2026', '20/10/2026', '20/10/2026']);
  });

  it('with a split read, the read\'s SO date wins over the board\'s', async () => {
    serveSplits({ 'pso-so-1': { ...LINE3_READ(), so_date: '2026-10-21' } });
    const board = oneDraftBoard();
    await mountWith(
      { ...board, orders: board.orders.map((o) => ({ ...o, so_date: '2026-10-20' })) } as unknown as Board,
      ['SO000001'],
    );
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    expect(firstCells(page)).toEqual(['21/10/2026']);
  });
});

describe('OI-SPLIT-CONFIRM-POLISH: the footer (owner, 21 Oct ~22:55)', () => {
  const footerIds = () =>
    Array.from(screen.getByTestId('confirm-guide-footer').querySelectorAll('button')).map(
      (button) => button.getAttribute('data-testid'),
    );

  it('Review split: Cancel far left, then Next at the right', async () => {
    await mountWith(oneEditedBoard(), ['SO000001']);
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    expect(footerIds()).toEqual(['confirm-guide-cancel', 'confirm-guide-next']);
  });

  it('Confirm step: the Confirm button is in the footer at the right, Back immediately left of it, Cancel far left', async () => {
    await mountWith(oneEditedBoard(), ['SO000001']);
    await walkToConfirmStep();
    const confirm = screen.getByTestId('confirm-guide-confirm');
    expect(screen.getByTestId('confirm-guide-footer')).toContainElement(confirm);
    expect(footerIds()).toEqual(['confirm-guide-cancel', 'confirm-guide-back', 'confirm-guide-confirm']);
    expect(confirm).toHaveTextContent('Confirm 1 order');
  });
});

describe('OI-SPLIT-CONFIRM-POLISH: the Review split page', () => {
  const FH1 = demand({ project_line_id: 'pl-1-1', line_no: 1, item_code: 'C-FH14', fulfilment_location: 'BRW-ED', qty: '40' });
  const FH2 = demand({
    project_line_id: 'pl-1-2',
    line_no: 2,
    item_code: 'C-FH14',
    fulfilment_location: 'BRW-ED',
    qty: '20',
    required_date: '2026-10-19',
  });
  const fhLine = (no: number, qty: number, date: string, splits: ReturnType<typeof wireSplit>[] = []) =>
    wireLine(no, 'C-FH14', qty, date, {
      line_id: `pl-1-${no}`,
      location: 'BRW-ED',
      split_state: 'acting',
      split_view: { status: 'saved' },
      splits,
    });
  const FH_READ = () => ({
    ...splitRead('pso-so-1', 'SO000001', []),
    lines: [
      fhLine(1, 40, '2026-09-20', [
        wireSplit('fh-a', 20, '2026-09-20', 'pl-1-1'),
        wireSplit('fh-b', 20, '2026-10-19', 'pl-1-2'),
      ]),
      fhLine(2, 20, '2026-10-19'),
    ],
  });
  const FH_UNSPLIT_READ = () => ({
    ...splitRead('pso-so-1', 'SO000001', []),
    lines: [fhLine(1, 40, '2026-09-20'), fhLine(2, 20, '2026-10-19')],
  });
  const fhBoard = () =>
    withDraft(withSplitEdited(boardOf([FH1, FH2]), ['pl-1-1']), ['pl-1-1', 'pl-1-2'], {
      'pl-1-1': 'ORDER',
      'pl-1-2': 'USE BRW',
    });
  const WARNING = 'Save or undo your split changes first';

  async function openFh(read: () => unknown = FH_READ) {
    serveSplits({ 'pso-so-1': read() });
    await mountWith(fhBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-1');
    return page;
  }
  const headers = (page: HTMLElement) =>
    within(page)
      .getAllByRole('columnheader')
      .map((th) => th.textContent?.trim() || th.getAttribute('aria-label') || '');
  const expectClean = (page: HTMLElement) => {
    expect(within(page).getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(within(page).getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
    expect(screen.queryByText(WARNING)).not.toBeInTheDocument();
  };

  it('1: no drag handle, no grip column and no draggable "N left" chip on the page', async () => {
    const page = await openFh();
    expect(page.querySelector('[data-drag-handle]')).toBeNull();
    expect(within(page).queryByRole('button', { name: /^Drag / })).not.toBeInTheDocument();
    expect(headers(page)).not.toContain('Drag');
    // a gap still reads "N left", as text
    typeQty(1, 1, '15');
    expect(within(page).getByTestId('balance-1')).toHaveTextContent('5 left');
    expect(page.querySelector('[data-drag-handle]')).toBeNull();
  });

  // every split of line 1 sits on line 2: line 1's own row is the base cells only
  const FH_ALL_MOVED_READ = () => ({
    ...splitRead('pso-so-1', 'SO000001', []),
    lines: [fhLine(1, 40, '2026-09-20', [wireSplit('fh-c', 40, '2026-10-19', 'pl-1-2')]), fhLine(2, 20, '2026-10-19')],
  });

  it.each([
    ['part moved', FH_READ],
    ['all moved', FH_ALL_MOVED_READ],
  ])('1: no row carries a grip cell, so every body column sits under its header (%s)', async (_name, read) => {
    const page = await openFh(read);
    // the only pinned cells left are the item code's (a grip cell is pinned and empty)
    const pinned = Array.from(page.querySelectorAll('td[data-pinned]'));
    expect(pinned.length).toBeGreaterThan(0);
    for (const cell of pinned) expect(cell).toHaveTextContent('C-FH14');
    // the first row of each line block: base cells + Breakdown qty/date + Remark + Balance + remove
    const heads = within(page).getAllByRole('columnheader').length;
    for (const body of Array.from(page.querySelectorAll('tbody[data-line-id]'))) {
      const first = body.querySelector('tr')!;
      const span = Array.from(first.querySelectorAll('td')).reduce((sum, td) => sum + (td.colSpan || 1), 0);
      expect(span).toBe(heads);
    }
  });

  it('2: the editable split columns read BREAKDOWN QTY and BREAKDOWN DATE; the email columns are unchanged', async () => {
    const page = await openFh();
    const names = headers(page).map((h) => h.toLowerCase());
    expect(names).toEqual(
      expect.arrayContaining(['qty', 'new qty', 'delivery date', 'new date', 'breakdown qty', 'breakdown date', 'remark']),
    );
    expect(names).not.toContain('change quantity');
    expect(names).not.toContain('change date');
  });

  // owner, SO427002 (21 Oct ~22:55): SO DATE was blank on first open of Review split
  const SO_DATE = '20/10/2026';
  const firstCells = (page: HTMLElement) =>
    Array.from(page.querySelectorAll('tbody[data-line-id]')).map((body) => body.querySelector('td')?.textContent ?? '');
  const datedRead = (read: () => { lines: unknown[] }) => () => ({ ...read(), so_date: '2026-10-20' });

  it('5: SO DATE is filled on every row on first open, and is the same after an edit and Undo', async () => {
    const page = await openFh(datedRead(FH_READ));
    expect(firstCells(page).length).toBeGreaterThan(0);
    expect(firstCells(page).every((text) => text === SO_DATE)).toBe(true);
    typeQty(1, 1, '15');
    fireEvent.click(within(page).getByRole('button', { name: 'Undo' }));
    await waitFor(() => expectClean(page));
    expect(firstCells(page).every((text) => text === SO_DATE)).toBe(true);
  });

  it('5: a covered line the split read does not list still shows the SO date read for the order', async () => {
    // line 2 is covered on the board but missing from the read: it is a read-only row under the editor
    const onlyLine1 = () => ({ ...splitRead('pso-so-1', 'SO000001', []), lines: [fhLine(1, 40, '2026-09-20')] });
    const page = await openFh(datedRead(onlyLine1));
    await within(page).findByTestId('split-line-2');
    expect(within(page).getAllByRole('table', { name: 'Split delivery sheet' })).toHaveLength(2);
    expect(firstCells(page)).toEqual([SO_DATE, SO_DATE]);
  });

  it('3: opens clean on a saved split: Save and Undo off, Next: Confirm on, no warning', async () => {
    const page = await openFh();
    expectClean(page);
  });

  it('3: opens clean on unsplit saved lines too, and stays clean after clicking through every cell', async () => {
    const page = await openFh(FH_UNSPLIT_READ);
    expectClean(page);
    for (const button of within(page).queryAllByRole('button', { name: /^Split line \d+ (quantity|date)$/ })) {
      await userEvent.click(button);
      await userEvent.click(screen.getByTestId('confirm-guide-steps'));
    }
    for (const field of Array.from(page.querySelectorAll<HTMLElement>('input, textarea'))) {
      await userEvent.click(field);
      await userEvent.click(screen.getByTestId('confirm-guide-steps'));
    }
    expectClean(page);
  });

  it('3: the warning shows only after a real edit, and Undo puts the page back to clean', async () => {
    const page = await openFh();
    expectClean(page);
    typeQty(1, 1, '15');
    expect(screen.getByText(WARNING)).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    fireEvent.click(within(page).getByRole('button', { name: 'Undo' }));
    await waitFor(() => expectClean(page));
  });

  it('4: every data column has a resize handle on its header edge; dragging it widens the column', async () => {
    const page = await openFh();
    const ths = within(page).getAllByRole('columnheader');
    const qtyTh = ths.find((th) => th.textContent?.trim().toLowerCase() === 'qty')!;
    const handle = qtyTh.querySelector<HTMLElement>('.cursor-col-resize');
    expect(handle).not.toBeNull();
    const before = parseFloat(qtyTh.style.width);
    expect(before).toBeGreaterThan(0);
    fireEvent.mouseDown(handle!, { clientX: 100 });
    fireEvent.mouseMove(document, { clientX: 160 });
    fireEvent.mouseUp(document, { clientX: 160 });
    await waitFor(() => expect(parseFloat(qtyTh.style.width)).toBe(before + 60));
    // the sheet grows to its columns (REMARK keeps its minimum) instead of squeezing REMARK
    const table = within(page).getByRole('table', { name: 'Split delivery sheet' });
    const fixed = Array.from(ths)
      .map((th) => parseFloat(th.style.width))
      .filter((width) => !Number.isNaN(width))
      .reduce((sum, width) => sum + width, 0);
    expect(parseFloat(table.style.getPropertyValue('--sheet-min'))).toBe(fixed + 100);
    // a phone hides SO date, S/O no and Location (80 + 76 + 64), so its floor leaves them out
    expect(parseFloat(table.style.getPropertyValue('--sheet-min-phone'))).toBe(fixed + 100 - 220);
    // REMARK takes whatever width the others leave, so its edge moves with theirs
    const named = ths.filter((th) => th.textContent?.trim() && th.textContent.trim().toLowerCase() !== 'remark');
    expect(named.length).toBeGreaterThan(8);
    for (const th of named) expect(th.querySelector('.cursor-col-resize')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// FULFIL-SO-REMARK (AC-8, AC-9, AC-10): the Remark field and Mockup badges on each SO page
// ---------------------------------------------------------------------------

describe('FULFIL-SO-REMARK: the Remark field and Mockup badge on each SO page', () => {
  /** `is_mockup` on the named lines; every other contribution is not a mockup line. */
  function withMockup(board: Board, lineIds: string[]) {
    return mapContributions(board, (entry) => ({
      ...entry,
      is_mockup: lineIds.includes(String(entry.project_line_id)),
    }));
  }

  /** `remark_type` on the named orders' standings (by sales_order_id). */
  function withRemarkType(board: Board, types: Record<string, string | null>) {
    return {
      ...board,
      orders: board.orders.map((o) =>
        o.sales_order_id in types ? { ...o, remark_type: types[o.sales_order_id] } : o,
      ),
    } as unknown as Board;
  }

  const remarkInput = (so: string) =>
    within(pageOf(so)).getByTestId('confirm-guide-so-remark') as HTMLInputElement;

  // SO000001: line 1 split-edited + line 3 saved draft are covered, line 2 is not.
  const base = () =>
    withDraft(withSplitEdited(boardOf([SO1_L1, SO1_L2, SO1_L3, SO2_L1]), ['pl-1-1']), ['pl-1-3', 'pl-2-1']);

  async function openAt(board: Board) {
    await mountWith(board);
    await openConfirmGuide();
    await screen.findAllByTestId('confirm-guide-split-page');
  }

  it('AC-8: prefills Mockup under the SO header when a chosen line is a mockup line', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    const input = remarkInput('SO000001');
    expect(input).toHaveValue('Mockup');
    expect(input).toHaveAttribute('maxLength', '100');
    expect(within(pageOf('SO000001')).getByLabelText('Remark')).toBe(input);
  });

  it('AC-8: Sponsorship beats Mockup and Purchase Request fills for its own order', async () => {
    await openAt(withRemarkType(withMockup(base(), ['pl-1-1']), { 'so-1': 'Sponsorship', 'so-2': 'Purchase Request' }));
    expect(remarkInput('SO000001')).toHaveValue('Sponsorship');
    await clickNext();
    expect(remarkInput('SO000002')).toHaveValue('Purchase Request');
  });

  it('AC-8: blank when no chosen line is a mockup line, even if an unchosen line is', async () => {
    await openAt(withMockup(base(), ['pl-1-2']));
    expect(remarkInput('SO000001')).toHaveValue('');
  });

  it('review 6: the Clear remark control is the shared Button inside the shared InputWrapper', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    const clear = within(pageOf('SO000001')).getByRole('button', { name: 'Clear remark' });
    expect(clear.tagName).toBe('BUTTON');
    expect(clear).toHaveAttribute('data-slot', 'button');
    const wrapper = clear.closest('[data-slot="input-wrapper"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper).toContainElement(remarkInput('SO000001'));
  });

  it('AC-8: the clear button empties the field and the field is editable', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    fireEvent.change(remarkInput('SO000001'), { target: { value: 'Sample for client' } });
    expect(remarkInput('SO000001')).toHaveValue('Sample for client');
    fireEvent.click(within(pageOf('SO000001')).getByRole('button', { name: 'Clear remark' }));
    expect(remarkInput('SO000001')).toHaveValue('');
  });

  it('AC-8: closing and reopening the guide recomputes the default; an edit is not kept', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    fireEvent.change(remarkInput('SO000001'), { target: { value: 'edited' } });
    click('confirm-guide-cancel');
    await waitFor(() => expect(screen.queryByTestId('confirm-guide')).not.toBeInTheDocument());
    await openConfirmGuide();
    await screen.findAllByTestId('confirm-guide-split-page');
    expect(remarkInput('SO000001')).toHaveValue('Mockup');
  });

  it('AC-9: mixed chosen lines badge only the mockup line', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    const page = pageOf('SO000001');
    const badges = within(page).getAllByTestId('confirm-guide-mockup-badge');
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent('Mockup');
    expect(within(within(page).getByTestId('split-line-1')).getByTestId('confirm-guide-mockup-badge')).toBeInTheDocument();
    expect(within(within(page).getByTestId('split-line-3')).queryByTestId('confirm-guide-mockup-badge')).toBeNull();
  });

  it('AC-9: when every chosen line is a mockup line, or none is, no line shows the badge', async () => {
    await openAt(withMockup(base(), ['pl-1-1', 'pl-1-3']));
    expect(within(pageOf('SO000001')).queryAllByTestId('confirm-guide-mockup-badge')).toHaveLength(0);
  });

  it('AC-10: Confirm sends so_remark for every order: the field value, "" when cleared', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    fireEvent.change(remarkInput('SO000001'), { target: { value: 'Sample for client' } });
    await clickNext();
    fireEvent.change(remarkInput('SO000002'), { target: { value: 'Temp' } });
    fireEvent.click(within(pageOf('SO000002')).getByRole('button', { name: 'Clear remark' }));
    await walkConfirmGuide();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    const byPso = Object.fromEntries(body.orders.map((o: { pso_id: string; so_remark?: string }) => [o.pso_id, o.so_remark]));
    expect(byPso).toEqual({ 'pso-so-1': 'Sample for client', 'pso-so-2': '' });
  });

  it('AC-10: an untouched default is posted as typed, not left out', async () => {
    await openAt(withMockup(base(), ['pl-1-1']));
    await walkConfirmGuide();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    expect(body.orders.find((o: { pso_id: string }) => o.pso_id === 'pso-so-1').so_remark).toBe('Mockup');
    expect(body.orders.find((o: { pso_id: string }) => o.pso_id === 'pso-so-2').so_remark).toBe('');
  });
});

/*
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): after a board Save, Confirm showed the old
 * decision's words until a page refresh, and a delivered line a pending change names read
 * "Delivered in full: nothing goes to purchasing" with a blank NEW DATE while the email prints
 * its Was -> Now. Popup = email = Excel.
 */
describe('CONFIRM-PREVIEW-STALE: Confirm reads the server fresh', () => {
  function boardWithRemark(remark: string, decision: Record<string, unknown>, savedAt: string) {
    return mapContributions(boardOf([SO1_L3]), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? {
            ...entry,
            saved_remark: remark,
            draft: { decision, saved_by: 'Test Planner', saved_at: savedAt },
          }
        : entry,
    );
  }

  it('opening Confirm re-reads the board and waits for it: the page prints the newest saved words', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('ORDER BACK', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    const reads = getPlanningBoard.mock.calls.length;
    // The board moved on the server (a Save elsewhere, or this tab's save reply carried no
    // `saved_remark`): the next read says ORDER 3.
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER 3', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
    );
    await openConfirmGuide();
    await waitFor(() => expect(getPlanningBoard.mock.calls.length).toBeGreaterThan(reads));
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(block).toHaveTextContent('ORDER 3'));
    expect(block).not.toHaveTextContent('ORDER BACK');
  });

  it('a newer server decision replaces the one this tab holds, and the planner is told', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('ORDER BACK', { verdict: 'amended', buy_qty: '0' }, '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    // Another tab saved a newer decision for the same line.
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER 3', { verdict: 'amended', buy_qty: '3' }, '2026-11-02T02:00:00Z'),
    );
    await openConfirmGuide();
    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('saved again')),
    );
  });

  it('a board read carrying the same saved draft this tab holds is not "saved again"', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('ORDER 3', { verdict: 'amended', buy_qty: '3' }, '2026-11-02T02:00:00Z'),
      ['SO000001'],
    );
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER 3', { verdict: 'amended', buy_qty: '3' }, '2026-11-02T02:00:00Z'),
    );
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    expect(toast.warning).not.toHaveBeenCalledWith(expect.stringContaining('saved again'));
  });

  it('a delivered line a pending change names prints its NEW DATE and no "nothing goes" note', async () => {
    const read = LINE3_READ();
    read.lines = [
      {
        ...wireLine(3, 'ZZT-ITEM-1C', 0, '2026-09-28', {
          line_id: 'pl-1-3',
          delivered_qty: 3,
          now_qty: 0,
          now_date: '2026-11-02',
          pending_change: true,
          new_date: '2026-11-02',
          remark_generated: 'DELAY',
          split_state: 'acting',
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
    expect(within(block).getByTestId('new-date-3')).toHaveTextContent('02/11/2026');
    expect(block).not.toHaveTextContent('nothing goes to purchasing');
    expect(block.querySelectorAll('input')).toHaveLength(0);
  });

  it('the newer server decision is the one Confirm posts, not the one this tab held', async () => {
    const amended = (buy: string, reserve: string) => ({
      verdict: 'amended',
      timely_spo_qty: '0',
      reserve_qty: reserve,
      reserve: Number(reserve) > 0 ? [{ warehouse_id: 'wh-brw', location: 'BRW-IB', qty: reserve }] : [],
      borrow: [],
      buy_qty: buy,
      reason: 'Planner choice.',
    });
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('USE OWN 10', amended('0', '10'), '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER 7', amended('7', '3'), '2026-11-02T02:00:00Z'),
    );
    await walkConfirmGuide();
    await waitFor(() =>
      expect(previewConfirmMany.mock.calls.length + confirmMany.mock.calls.length).toBeGreaterThan(0),
    );
    // The press's body is its own dry run; the post is that body narrowed.
    const posted = JSON.stringify(pressDryRuns().at(-1));
    expect(posted).toContain('"buy_qty":"7"');
    expect(posted).not.toContain('"qty":"10"');
  });

  it("this tab's own save is recorded: the next board read carrying it is not \"saved again\"", async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('ORDER BACK', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    putLineDraft.mockResolvedValue({
      decision: { verdict: 'approved', remark: 'URGENT' },
      saved_by: 'Test Planner',
      saved_at: '2026-11-02T03:00:00Z',
    });
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    // What the server holds once this tab's save landed: the save reply's own saved_at.
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER BACK', { verdict: 'approved', remark: 'URGENT' }, '2026-11-02T03:00:00Z'),
    );
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'URGENT' } });
    const reads = getPlanningBoard.mock.calls.length;
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(putLineDraft).toHaveBeenCalled());
    // The save says which draft it stands on, so the server can refuse it over a newer one.
    expect(putLineDraft.mock.calls[0][3]).toBe('2026-11-02T01:00:00Z');
    // The remark save re-reads the board (`saveLineRemarks`), which now carries that draft.
    await waitFor(() => expect(getPlanningBoard.mock.calls.length).toBeGreaterThan(reads));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(toast.warning).not.toHaveBeenCalledWith(expect.stringContaining('saved again'));
  });

  it('a failed re-read on open writes nothing from the stale view: no Next, a Retry', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(
      boardWithRemark('ORDER BACK', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    // The board query retries once: both tries time out.
    getPlanningBoard
      .mockRejectedValueOnce(new Error('The server took too long to answer.'))
      .mockRejectedValueOnce(new Error('The server took too long to answer.'));
    await openConfirmGuide();
    const failed = await screen.findByTestId('confirm-guide-refresh-failed');
    expect(failed).toHaveTextContent('could not be read again');
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    expect(screen.queryByTestId('split-line-3')).not.toBeInTheDocument();
    // Retry reads again; once it answers the page is usable.
    getPlanningBoard.mockResolvedValue(
      boardWithRemark('ORDER 3', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
    );
    fireEvent.click(within(failed).getByRole('button', { name: 'Retry' }));
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    expect(screen.queryByTestId('confirm-guide-refresh-failed')).not.toBeInTheDocument();
  });

  // Round 3 (crew final pass, 2 Nov): the REMARK is the purchasing email's own, from the
  // press's dry run, never the board's saved-decision words (popup = email = Excel).
  it('the page prints the email\'s REMARK from the dry run, not the board\'s saved words', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    dryRunAnswers({
      'pso-so-1': { email: [{ so_line_id: 'pl-1-3', remark: 'DELAY, CHANGED: ORDER 25 -> USE BRW-BB 5 & ORDER 20' }] },
    });
    await mountWith(
      boardWithRemark('CHANGED: ORDER 25 -> USE BRW-BB 5 & ORDER 20', { verdict: 'approved' }, '2026-11-02T01:00:00Z'),
      ['SO000001'],
    );
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() =>
      expect(block).toHaveTextContent('DELAY, CHANGED: ORDER 25 -> USE BRW-BB 5 & ORDER 20'),
    );
    // Nothing was posted: the words came from a dry run.
    expect(confirmMany).not.toHaveBeenCalled();
  });

  it('a line the email does not tell reads no remark, not the board\'s words', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    dryRunAnswers({ 'pso-so-1': { email: [] } });
    await mountWith(boardWithRemark('ORDER', { verdict: 'approved' }, '2026-11-02T01:00:00Z'), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(previewConfirmMany).toHaveBeenCalled());
    // The editable row's REMARK is its input (value, else the default words).
    await waitFor(() =>
      expect((within(block).getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe(''),
    );
  });

  // Review round 3 (S1): one quiet email dry run per board read, never a storm.
  it('opening the guide runs ONE quiet email dry run, and none more while nothing changes', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(boardWithRemark('ORDER', { verdict: 'approved' }, '2026-11-02T01:00:00Z'), ['SO000001']);
    await openConfirmGuide();
    await screen.findByTestId('split-line-3');
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(emailDryRuns()).toHaveLength(1);
    expect(pressDryRuns()).toHaveLength(0);
  });

  // CONFIRM-DIALOG-SPEED (owner, 3 Nov 2026): Next no longer waits for the words; only the
  // Confirm step does (see that lane's own block below).
  it('after a save the sheet stays up with the last words while the new ones are read', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    dryRunAnswers({ 'pso-so-1': { email: [{ so_line_id: 'pl-1-3', remark: 'DELAY' }] } });
    await mountWith(boardWithRemark('ORDER', { verdict: 'approved' }, '2026-11-02T01:00:00Z'), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    // The next email dry run is held open.
    let answer: (value: unknown) => void = () => {};
    previewConfirmMany.mockImplementationOnce(
      () => new Promise((resolve) => {
        answer = resolve;
      }),
    );
    putLineDraft.mockResolvedValue({
      decision: { verdict: 'approved', remark: 'URGENT' },
      saved_by: 'Test Planner',
      saved_at: '2026-11-02T03:00:00Z',
    });
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'URGENT' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(emailDryRuns().length).toBeGreaterThan(1));
    // Still the sheet, never the loading skeleton, and the page says the words are being read.
    expect(screen.getByTestId('split-line-3')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-words-loading')).toBeInTheDocument();
    answer({ results: [{ pso_id: 'pso-so-1', ok: true, preview: true, email_lines: [{ so_line_id: 'pl-1-3', remark: 'URGENT' }] }] });
    await waitFor(() =>
      expect(screen.queryByTestId('confirm-guide-words-loading')).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  });

  it('the email dry run is quiet and leaves out an order with no planning record', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    // SO000002 has no planning record yet (its adopt is held open), and a saved decision.
    adoptSalesOrder.mockImplementation(() => new Promise(() => {}));
    const board = mapContributions(
      boardOf([SO1_L3, { ...SO2_L1, project_sales_order_id: null } as BoardDemandLine]),
      (entry) => ({
        ...entry,
        saved_remark: 'ORDER',
        draft: { decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-11-02T01:00:00Z' },
      }),
    );
    await mountWith(board, ['SO000001', 'SO000002']);
    await openConfirmGuide();
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    const [body] = emailDryRuns()[0] as [{ quiet: boolean; orders: { pso_id: string }[] }];
    expect(body.quiet).toBe(true);
    expect(body.orders.every((order) => Boolean(order.pso_id))).toBe(true);
  });
});

/*
 * CONFIRM-REMARK-FIX (crew re-check of #2091, 3 Nov 2026): a save ran TWO email dry runs (one
 * on the save's cache patch, one on the board re-read), every dry run covered the whole press,
 * and a superseded one kept running. One dry run per board read, for the order on screen, at
 * most one in flight.
 */
describe('CONFIRM-REMARK-FIX: one email dry run per read, for the order on screen', () => {
  const emailOrders = () =>
    emailDryRuns().map(([body]) =>
      (body as { orders: { pso_id: string }[] }).orders.map((order) => order.pso_id),
    );

  function savedBoard() {
    return mapContributions(boardOf([SO1_L3]), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? {
            ...entry,
            saved_remark: 'ORDER',
            draft: { decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-11-02T01:00:00Z' },
          }
        : entry,
    );
  }

  it('F3: a remark save runs ONE more email dry run, after the board re-read', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(savedBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    expect(emailDryRuns()).toHaveLength(1);
    putLineDraft.mockResolvedValue({
      decision: { verdict: 'approved', remark: 'URGENT' },
      saved_by: 'Test Planner',
      saved_at: '2026-11-02T03:00:00Z',
    });
    const reads = getPlanningBoard.mock.calls.length;
    // The re-read takes a while, as over the network: the save's cache patch lands first.
    const board = savedBoard();
    getPlanningBoard.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(board), 120)),
    );
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'URGENT' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(getPlanningBoard.mock.calls.length).toBeGreaterThan(reads));
    await waitFor(() => expect(emailDryRuns()).toHaveLength(2), { timeout: 2000 });
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(emailDryRuns()).toHaveLength(2);
  });

  it('the email dry run carries only the order on screen; the next page runs its own once', async () => {
    serveSplits({ 'pso-so-1': SO1_READ(), 'pso-so-2': SO2_READ() });
    await mountWith(coveredBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    await waitFor(() => expect(emailOrders()).toEqual([['pso-so-1']]));
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    await clickNext();
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000002'),
    );
    await waitFor(() => expect(emailOrders()).toEqual([['pso-so-1'], ['pso-so-2']]));
    // Back to a page already read for this board read: no new dry run.
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    click('confirm-guide-back');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001'),
    );
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(emailOrders()).toEqual([['pso-so-1'], ['pso-so-2']]);
  });

  it('Back while a page\'s dry run is out cancels it quietly: no "could not be read", Next works', async () => {
    serveSplits({ 'pso-so-1': SO1_READ(), 'pso-so-2': SO2_READ() });
    await mountWith(coveredBoard());
    await openConfirmGuide();
    await screen.findByTestId('confirm-guide-split-page');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    // Page 2's dry run is held open and rejects on abort, as `fetch` does.
    previewConfirmMany.mockImplementationOnce(
      (_body: unknown, signal?: AbortSignal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted.', 'AbortError')),
          );
        }),
    );
    await clickNext();
    await waitFor(() => expect(emailOrders()).toEqual([['pso-so-1'], ['pso-so-2']]));
    click('confirm-guide-back');
    await waitFor(() =>
      expect(screen.getByTestId('confirm-guide-split-page')).toHaveAttribute('data-so', 'SO000001'),
    );
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(screen.queryByTestId('confirm-guide-refresh-failed')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  });

  it('a superseded email dry run is cancelled: at most one in flight; the same body is not re-run', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(savedBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    // The next email dry run is held open; a second save re-reads the board meanwhile.
    previewConfirmMany.mockImplementationOnce(() => new Promise(() => {}));
    putLineDraft.mockResolvedValue({
      decision: { verdict: 'approved', remark: 'URGENT' },
      saved_by: 'Test Planner',
      saved_at: '2026-11-02T03:00:00Z',
    });
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'URGENT' } });
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(emailDryRuns()).toHaveLength(2));
    const held = previewConfirmMany.mock.calls.findLast(([body]) => Boolean((body as { quiet?: boolean }).quiet));
    const heldSignal = held?.[1] as AbortSignal | undefined;
    expect(heldSignal).toBeDefined();
    expect(heldSignal?.aborted).toBe(false);
    // CONFIRM-DIALOG-SPEED: another board read carrying the SAME body leaves the run out
    // standing (no second 40 s dry run for nothing).
    await act(async () => {
      await lastClient?.refetchQueries({ type: 'active' });
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(emailDryRuns()).toHaveLength(2);
    expect(heldSignal?.aborted).toBe(false);
    // A read whose decision moved (a newer save elsewhere) cancels it and runs again.
    getPlanningBoard.mockResolvedValue(
      mapContributions(boardOf([SO1_L3]), (entry) =>
        entry.project_line_id === 'pl-1-3'
          ? {
              ...entry,
              saved_remark: 'ORDER',
              draft: {
                decision: { verdict: 'approved', remark: 'ELSEWHERE' },
                saved_by: 'Another Planner',
                saved_at: '2026-11-02T05:00:00Z',
              },
            }
          : entry,
      ),
    );
    await act(async () => {
      await lastClient?.refetchQueries({ type: 'active' });
    });
    await waitFor(() => expect(emailDryRuns()).toHaveLength(3));
    expect(heldSignal?.aborted).toBe(true);
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  });
});

/*
 * NO-AC-MOVED-WARNING (owner, 3 Nov 2026, prod SO423361): "I already decided so why are you
 * still suggesting to me ... the warning shouldn't even appear." A saved decision stands
 * silently on the Review split, as before #2091: no suggestion, no Keep, no Take suggestion.
 */
describe('NO-AC-MOVED-WARNING: a saved decision is never second-guessed by the change suggestion', () => {
  const BATCH = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE;
  // The batch row `pcr-381895-1` names this line and suggests Buy 25 (was 10).
  const NAMED = demand({
    sales_order_id: 'so-381895',
    so_number: 'SO381895',
    project_sales_order_id: 'pso-381895',
    project_line_id: 'pl-381895-1',
    line_no: 1,
    item_code: 'SRTWCX7405-RL-S-PJ',
    qty: '25',
    required_date: '2026-09-20',
  });
  // What the planner saved: Borrow 25 from another location, not the suggested Buy.
  const SAVED_BORROW = {
    verdict: 'amended',
    timely_spo_qty: '0',
    reserve: [],
    borrow: [{ qty: '25', warehouse_id: 'wh-brw-bb', location: 'BRW-BB', donor_project_id: null }],
    buy_qty: '0',
    reason: 'Order back already raised.',
  };
  const boardWithSavedBorrow = () =>
    mapContributions(buildBoard([NAMED], { today: TODAY, freeStock: {}, granularity: 'week' }), (entry) =>
      entry.project_line_id === 'pl-381895-1'
        ? {
            ...entry,
            saved_remark: 'BORROW BRW-BB 25',
            draft: { decision: SAVED_BORROW, saved_by: 'Test Planner', saved_at: '2026-11-02T01:00:00Z' },
          }
        : entry,
    );

  async function mountOnBatch() {
    getPlanningChangeBatch.mockResolvedValue(BATCH);
    getPlanningBoard.mockResolvedValue(boardWithSavedBorrow());
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <FulfilmentBoardPanel soNumbers={['SO381895']} batchId={BATCH.id} onBack={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByTestId('fulfilment-board-matrix');
    await waitFor(() => expect(getPlanningChangeBatch).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
  }

  it('the Review split shows no "AutoCount moved this line", no Keep, no Take suggestion; Next is on', async () => {
    await mountOnBatch();
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    expect(page).toHaveTextContent('SRTWCX7405-RL-S-PJ');
    expect(screen.getByTestId('confirm-guide')).not.toHaveTextContent('AutoCount moved this line');
    expect(screen.queryByTestId('confirm-guide-moved')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Keep' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take suggestion' })).not.toBeInTheDocument();
  });

  it('Confirm proceeds with the saved Borrow, never the change suggestion, and the Confirm step says nothing of it', async () => {
    await mountOnBatch();
    const confirm = await walkToConfirmStep();
    expect(confirm).not.toBeNull();
    expect(screen.getByTestId('confirm-guide')).not.toHaveTextContent('AutoCount moved this line');
    expect(screen.queryByRole('button', { name: 'Take suggestion' })).not.toBeInTheDocument();
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm as HTMLElement);
    await waitFor(() => expect(pressDryRuns().length).toBeGreaterThan(0));
    const posted = JSON.stringify(pressDryRuns().at(-1));
    expect(posted).toContain('"qty":"25"');
    expect(posted).toContain('wh-brw-bb');
    expect(posted).toContain('"buy_qty":"0"');
    expect(toast.warning).not.toHaveBeenCalledWith(expect.stringContaining('suggest'));
    expect(toast.success).not.toHaveBeenCalledWith(expect.stringContaining('suggest'));
  });
});

/*
 * CONFIRM-DIALOG-SPEED (owner, 3 Nov 2026, prod SO423361: "Review split" sat on its skeleton):
 * the Review split waits for the order's own fresh data only (the board re-read and its split
 * read), never for the email dry run, which runs behind it. The Confirm step waits for it.
 */
describe('CONFIRM-DIALOG-SPEED: the Review split never waits on the email dry run', () => {
  function savedBoard() {
    return mapContributions(boardOf([SO1_L3]), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? {
            ...entry,
            saved_remark: 'ORDER',
            draft: { decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-11-02T01:00:00Z' },
          }
        : entry,
    );
  }

  it('step 1 renders and is interactive while the email dry run is still pending', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    let answer: (value: unknown) => void = () => {};
    previewConfirmMany.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    );
    await mountWith(savedBoard(), ['SO000001']);
    await openConfirmGuide();
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    // The dry run is still out: the sheet is up, its Remark box editable, Next on.
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    expect(within(block).getByLabelText('Remark, line 3')).toBeEnabled();
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
    expect(screen.getByTestId('confirm-guide-words-loading')).toBeInTheDocument();
    // The Confirm step shows its own wait while the email's words are still being read.
    click('confirm-guide-next');
    const confirm = await screen.findByTestId('confirm-guide-confirm');
    expect(confirm).toBeDisabled();
    expect(screen.getByTestId('confirm-guide-words-loading')).toBeInTheDocument();
    // The Confirm step started no dry run of its own and did not cancel the one out.
    expect(emailDryRuns()).toHaveLength(1);
    const heldSignal = emailDryRuns()[0][1] as AbortSignal | undefined;
    expect(heldSignal?.aborted).toBe(false);
    await act(async () => {
      answer({
        results: [
          { pso_id: 'pso-so-1', ok: true, preview: true, email_lines: [{ so_line_id: 'pl-1-3', remark: 'ORDER' }] },
        ],
      });
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(screen.queryByTestId('confirm-guide-words-loading')).not.toBeInTheDocument();
    expect(pressDryRuns()).toHaveLength(0);
  });

  it('the email dry run starts as the guide opens, beside the board re-read, and stands when that read changes nothing', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(savedBoard(), ['SO000001']);
    const board = savedBoard();
    let release: () => void = () => {};
    getPlanningBoard.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve(board);
        }),
    );
    let answer: (value: unknown) => void = () => {};
    previewConfirmMany.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    );
    await openConfirmGuide();
    // The board re-read is still out, and the dry run is already running.
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    const heldSignal = emailDryRuns()[0][1] as AbortSignal | undefined;
    // The sheet still waits for the re-read.
    expect(screen.queryByTestId('split-line-3')).not.toBeInTheDocument();
    await act(async () => release());
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await new Promise((resolve) => setTimeout(resolve, 100));
    // Same body after the read: the run out stands, no second one.
    expect(emailDryRuns()).toHaveLength(1);
    expect(heldSignal?.aborted).toBe(false);
    expect(screen.getByTestId('confirm-guide-words-loading')).toHaveTextContent(
      'Preparing email preview...',
    );
    await act(async () => {
      answer({
        results: [
          { pso_id: 'pso-so-1', ok: true, preview: true, email_lines: [{ so_line_id: 'pl-1-3', remark: 'DELAY' }] },
        ],
      });
    });
    await waitFor(() => expect(within(page).getByTestId('split-line-3')).toHaveTextContent('DELAY'));
    expect(screen.queryByTestId('confirm-guide-words-loading')).not.toBeInTheDocument();
  });

  it('review B1: a split Save on the page runs the email preview again (the body carries no split rows); Confirm waits for it', async () => {
    const page = await openEditablePage();
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    await waitFor(() => expect(screen.queryByTestId('confirm-guide-words-loading')).not.toBeInTheDocument());
    await editLine3();
    serveSplits({ 'pso-so-1': LINE3_SPLIT_READ() });
    saveLineSplits.mockImplementation(() => Promise.resolve(LINE3_SPLIT_READ()));
    let answer: (value: unknown) => void = () => {};
    previewConfirmMany.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    );
    fireEvent.click(within(page).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(emailDryRuns()).toHaveLength(2));
    await clickNext();
    const confirm = await screen.findByTestId('confirm-guide-confirm');
    expect(confirm).toBeDisabled();
    await act(async () => {
      answer({ results: [{ pso_id: 'pso-so-1', ok: true, preview: true, email_lines: [] }] });
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(emailDryRuns()).toHaveLength(2);
  });

  it('review B2: a failed email preview keeps the sheet and its unsaved edit; only Confirm waits, behind its own Retry', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    let fail: (reason: unknown) => void = () => {};
    previewConfirmMany.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = reject;
        }),
    );
    await mountWith(oneDraftBoard(), ['SO000001']);
    await openConfirmGuide();
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await editLine3();
    await act(async () => fail(new Error('Gateway timeout')));
    await screen.findByTestId('confirm-guide-words-failed');
    // The editor is still there with the edit; no "board could not be read" in its place.
    expect(screen.queryByTestId('confirm-guide-refresh-failed')).not.toBeInTheDocument();
    expect(screen.getByText('Save or undo your split changes first')).toBeInTheDocument();
    expect((screen.getByLabelText('Date, line 3 split 2') as HTMLInputElement).value).toBe('20/10/2026');
    // Retry runs the preview again, nothing else.
    const reads = getPlanningBoard.mock.calls.length;
    fireEvent.click(within(screen.getByTestId('confirm-guide-words-failed')).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(emailDryRuns()).toHaveLength(2));
    await waitFor(() => expect(screen.queryByTestId('confirm-guide-words-failed')).not.toBeInTheDocument());
    expect(getPlanningBoard.mock.calls.length).toBe(reads);
  });

  it('review S1: words read for a body from before the re-read are never shown once the re-read changed the body', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(savedBoard(), ['SO000001']);
    // The re-read is held; the dry run on the tab's decisions answers first with OLD words.
    const moved = mapContributions(boardOf([SO1_L3]), (entry) =>
      entry.project_line_id === 'pl-1-3'
        ? {
            ...entry,
            saved_remark: 'FRESH',
            draft: {
              decision: { verdict: 'approved', suspected_system_issue: true },
              saved_by: 'Another Planner',
              saved_at: '2026-11-02T05:00:00Z',
            },
          }
        : entry,
    );
    let release: () => void = () => {};
    getPlanningBoard.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve(moved);
        }),
    );
    previewConfirmMany.mockImplementationOnce(() =>
      Promise.resolve({
        results: [{ pso_id: 'pso-so-1', ok: true, preview: true, email_lines: [{ so_line_id: 'pl-1-3', remark: 'OLD WORDS' }] }],
      }),
    );
    previewConfirmMany.mockImplementationOnce(() => new Promise(() => {}));
    await openConfirmGuide();
    await waitFor(() => expect(emailDryRuns()).toHaveLength(1));
    await act(async () => release());
    const page = await screen.findByTestId('confirm-guide-split-page');
    const block = await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(emailDryRuns()).toHaveLength(2));
    expect(block).not.toHaveTextContent('OLD WORDS');
    expect((within(block).getByLabelText('Remark, line 3') as HTMLInputElement).value).not.toBe('OLD WORDS');
    expect(screen.getByTestId('confirm-guide-words-loading')).toBeInTheDocument();
  });

  it('opening Confirm while the board is already reading joins that read, never a second one', async () => {
    serveSplits({ 'pso-so-1': LINE3_READ() });
    await mountWith(savedBoard(), ['SO000001']);
    const board = savedBoard();
    let release: () => void = () => {};
    getPlanningBoard.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve(board);
        }),
    );
    const reads = getPlanningBoard.mock.calls.length;
    // A read is already out (the board re-reading after a save elsewhere on the screen).
    act(() => {
      void lastClient?.refetchQueries({ type: 'active' });
    });
    await waitFor(() => expect(getPlanningBoard.mock.calls.length).toBe(reads + 1));
    await openConfirmGuide();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(getPlanningBoard.mock.calls.length).toBe(reads + 1);
    await act(async () => release());
    const page = await screen.findByTestId('confirm-guide-split-page');
    await within(page).findByTestId('split-line-3');
    await waitFor(() => expect(screen.getByTestId('confirm-guide-next')).toBeEnabled());
  });
});
