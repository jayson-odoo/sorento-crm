/**
 * OI-WHOLE-SO-CANCEL F2 (owner 00:06: "follow the path of Decide Confirm like normal
 * fulfilment planning"), red: a book-cancelled line is pre-marked "Change proposed" (Was = the
 * line's decision, Now = "Cancel line"), its only action is Save, "Save all suggested" includes
 * it, a saved cancel counts in "Confirm (N)", the button is ALWAYS "Confirm (N)" (never "Apply
 * AutoCount change"), the "Applies the AutoCount change ..." note is gone and the result reads
 * "<SO>: confirmed as revision N (M purchase rows handed over)". Harness from
 * `FulfilmentBoardPanel.handedOver.test.tsx` (list view).
 */
/**
 * OI-WHOLE-SO-CANCEL v2 (B1), red: the confirm result sentence counts the purchase rows the
 * press HANDED OVER (`inquiry_rows_handed_over`), not `inquiry_rows_created` (0 on a date
 * move, whose DELAY line is handed over without creating a row). Harness copied from
 * `FulfilmentBoardPanel.change.test.tsx`.
 *
 * (handedOver header) The board opened ON a planning-change batch (`PLAN-scm-cs-planning-uat.md` part 3).
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
  // R-J (List is now the default view): every spec here exercises the GRID matrix, so
  // `?view=grid` is seeded rather than clicking the Grid button in each test.
  useSearchParams: () => new URLSearchParams('view=list&scope=all'),
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

// OI-SPLIT-GUIDE (UAC F2): every guide page reads its order's split view; these specs only care
// about what the press posts, so the read answers an order with no lines.
vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: (psoId: string) =>
    Promise.resolve({ pso_id: psoId, so_number: psoId, customer: null, project: null, lines: [] }),
  saveLineSplits: vi.fn(),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { walkConfirmGuide } from '@/test-mocks/confirmGuide';
import {
  buildBoard,
  type BoardDemandLine,
} from '../../_shared/lib/__testsupport__/boardFixture';
import {
  MOCK_PLANNING_CHANGE_BATCH_PENDING,
  MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
} from '../../_shared/__mocks__/planningChanges';

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

/**
 * FULFIL-CONFIRM-SCOPE v2: Confirm is only offered after a Preview, so a test that used to press
 * the confirm dialog now previews first. The default preview answer echoes the lines the body
 * names (line number read off the fixture's `pl-<so>-<line_no>` ids), with no purchase rows.
 */
function defaultPreview(body: {
  orders: { pso_id: string; lines: { project_line_id: string }[]; rejected_line_ids?: string[] }[];
}) {
  return Promise.resolve({
    results: body.orders.map((order) => ({
      pso_id: order.pso_id,
      ok: true,
      preview: true,
      decision_revision: 1,
      lines_confirmed: order.lines.map((line) => ({
        project_line_id: line.project_line_id,
        line_no: Number(line.project_line_id.split('-').pop()),
        item_code: null,
      })),
      lines_carried: 0,
      lines_held_back: [],
      lines_withdrawn: (order.rejected_line_ids ?? []).map((id) => ({
        project_line_id: id,
        line_no: null,
        item_code: null,
      })),
      lines_fulfilled_skipped: 0,
      inquiry_rows: [],
      transfers: [],
    })),
  });
}

async function pressPreviewThenConfirm() {
  await waitFor(() => expect(screen.getByTestId('board-confirm')).toBeEnabled());
  await walkConfirmGuide();
}

beforeEach(() => {
  vi.clearAllMocks();
  previewConfirmMany.mockImplementation(defaultPreview);
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


/** One order whose ONLY pending line is book-cancelled: contribution flagged cancelled, the
 * batch's `cancelled` row naming it. */
function cancelOnlyBoard() {
  const batchRow = MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.orders[0].rows.find(
    (r) => r.kind === 'cancelled',
  )!;
  const base = buildBoard(
    [demand({ line_no: batchRow.line_no, project_line_id: batchRow.project_line_id })],
    { today: TODAY, freeStock: {}, granularity: 'week' },
  );
  const mark = (entry: (typeof base.contributions)[number]) => ({
    ...entry,
    qty: '0',
    cancelled: true,
    pending_change_batch_id: MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.id,
  });
  getPlanningChangeBatch.mockResolvedValue({
    ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE,
    orders: [{ ...MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.orders[0], rows: [batchRow] }],
  });
  getPlanningBoard.mockResolvedValue({
    ...base,
    cells: [],
    line_count: 0,
    contributions: base.contributions.map(mark),
    orders: base.orders.map((o: (typeof base.orders)[number]) => ({
      ...o,
      pending_change_batch_id: MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE.id,
    })),
  });
}

describe('F2: a cancelled line follows Decide -> Confirm', () => {
  it('is pre-marked "Change proposed" (Now = Cancel line), not "Cancelled"', async () => {
    cancelOnlyBoard();
    renderPanel();
    expect(await screen.findByText('Change proposed')).toBeInTheDocument();
    expect(screen.getByText(/Cancel line/)).toBeInTheDocument();
  });

  it('offers Save as its only action', async () => {
    cancelOnlyBoard();
    renderPanel();
    await screen.findByText('Change proposed');
    expect(screen.getAllByRole('button', { name: /^Save .* as suggested$/ })).toHaveLength(1);
    expect(screen.queryAllByRole('button', { name: /reject|amend|undo/i })).toHaveLength(0);
  });

  it('is counted only once saved, through Save all suggested, and the button is always Confirm (N)', async () => {
    cancelOnlyBoard();
    renderPanel();
    await screen.findByText('Change proposed');
    expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (0)');
    expect(screen.getByTestId('board-confirm')).not.toHaveTextContent('Apply AutoCount change');

    fireEvent.click(screen.getByRole('button', { name: /save all suggested/i }));

    await waitFor(() =>
      expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)'),
    );
    expect(screen.getByTestId('board-confirm')).not.toHaveTextContent('Apply AutoCount change');
  });

  it('shows no "Applies the AutoCount change" note', async () => {
    cancelOnlyBoard();
    renderPanel();
    await screen.findByText('Change proposed');
    expect(screen.queryByText(/Applies the AutoCount change/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('board-confirm-summary')).not.toHaveTextContent(
      'AutoCount change',
    );
  });

  it('reads the normal result sentence after the press', async () => {
    cancelOnlyBoard();
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-381895',
          ok: true,
          decision_revision: 5,
          planning_change_applied: true,
          lines_confirmed: [{ project_line_id: 'pl-381895-2', line_no: 2, item_code: null }],
          inquiry_rows_created: 0,
          inquiry_rows_handed_over: 3,
        },
      ],
    });
    renderPanel();
    await screen.findByText('Change proposed');
    fireEvent.click(screen.getByRole('button', { name: /save all suggested/i }));
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)'),
    );

    await pressPreviewThenConfirm();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));

    const results = await screen.findByTestId('board-confirm-results');
    expect(results).toHaveTextContent('confirmed as revision 5 (3 purchase rows handed over)');
    expect(results).not.toHaveTextContent('applied the AutoCount change');
  });
});
