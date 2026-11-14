/**
 * OI-WHOLE-SO-CANCEL v2 (B1), red: the confirm result sentence counts the purchase rows the
 * press HANDED OVER (`inquiry_rows_handed_over`), not `inquiry_rows_created` (0 on a date
 * move, whose DELAY line is handed over without creating a row). Harness copied from
 * `FulfilmentBoardPanel.change.test.tsx`.
 *
 * (original header) The board opened ON a planning-change batch (`PLAN-scm-cs-planning-uat.md` part 3).
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

describe('B1: the confirm sentence prints inquiry_rows_handed_over', () => {
  it('reads "1 purchase row handed over" when the result hands one over and creates none', async () => {
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-381895',
          ok: true,
          decision_revision: 3,
          inquiry_rows_created: 0,
          inquiry_rows_handed_over: 1,
        },
      ],
    });
    renderPanel();
    await screen.findByTestId('board-change-icon-pcr-381895-1');
    fireEvent.click(
      await screen.findByRole('button', {
        name: /SRTWCX7405-RL-S-PJ, .* across 1 sales order/,
      }),
    );
    const linesTab = await screen.findByRole('tab', { name: /^Contributing lines/ });
    fireEvent.mouseDown(linesTab);
    fireEvent.click(linesTab);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Save SO381895 line 1 as suggested' }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)'),
    );

    await pressPreviewThenConfirm();
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));

    const results = await screen.findByTestId('board-confirm-results');
    expect(results).toHaveTextContent('1 purchase row handed over');
    expect(results).not.toHaveTextContent('0 purchase rows');
  });
});

/** The press that reaches Confirm in the existing test above, answered with `result`. */
async function confirmWith(result: Record<string, unknown>) {
  confirmMany.mockResolvedValue({ results: [{ pso_id: 'pso-so-381895', ok: true, ...result }] });
  renderPanel();
  await screen.findByTestId('board-change-icon-pcr-381895-1');
  fireEvent.click(
    await screen.findByRole('button', { name: /SRTWCX7405-RL-S-PJ, .* across 1 sales order/ }),
  );
  const linesTab = await screen.findByRole('tab', { name: /^Contributing lines/ });
  fireEvent.mouseDown(linesTab);
  fireEvent.click(linesTab);
  fireEvent.click(await screen.findByRole('button', { name: 'Save SO381895 line 1 as suggested' }));
  await waitFor(() => expect(screen.getByTestId('board-confirm')).toHaveTextContent('Confirm (1)'));
  await pressPreviewThenConfirm();
  await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
  return screen.findByTestId('board-confirm-results');
}

describe('B1 regression (F2 12/13 Nov): a deleted SO reads the normal sentence', () => {
  it('prints "confirmed as revision N (3 purchase rows handed over)" once the cancels are saved, never the apply-only sentence', async () => {
    const results = await confirmWith({
      decision_revision: 3,
      planning_change_applied: true,
      lines_confirmed: [],
      inquiry_rows_created: 0,
      inquiry_rows_handed_over: 3,
      lines_retired: [
        { line_no: 1, item_code: 'ZZT-A' },
        { line_no: 2, item_code: 'ZZT-B' },
        { line_no: 3, item_code: 'ZZT-C' },
      ],
    });

    expect(results).toHaveTextContent('confirmed as revision 3 (3 purchase rows handed over)');
    expect(results).not.toHaveTextContent('applied the AutoCount change');
  });

  it('guard: a date-moved Buy (1 confirmed, 1 handed over, none created) still reads confirmed as revision N', async () => {
    const results = await confirmWith({
      decision_revision: 4,
      lines_confirmed: [{ project_line_id: 'pl-so-381895-1', line_no: 1, item_code: null }],
      inquiry_rows_created: 0,
      inquiry_rows_handed_over: 1,
    });

    expect(results).toHaveTextContent('confirmed as revision 4 (1 purchase row handed over)');
  });
});
