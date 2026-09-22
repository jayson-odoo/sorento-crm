/**
 * Review round (reviewer + security-reviewer finding, `PLAN-board-undo-last-confirm.md`):
 * the board's own gear-menu undo entries, over a MOCKED board payload carrying the real
 * `undo` field (S1 already lands this on the wire; this pins the PANEL's own read of it).
 *
 * AC-UC-02 two entries for two undoable orders of three; AC-UC-03 a refused entry is
 * disabled AND its reason text is VISIBLE in the item (not only in a `title` attribute -
 * the review round's own amendment to AC-UC-03, since a `title` never surfaces on a
 * screen reader or a touch device); AC-UC-04 no entry and no separator when nothing on
 * the board is undoable.
 *
 * Mirrors `FulfilmentBoardPanel.autobatch.test.tsx`'s scaffolding (same mocks, same
 * `renderPanel` shape, `buildBoard` fixture) rather than copying its assertions.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => new URLSearchParams('view=grid'),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const getPlanningBoard = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: vi.fn(),
  getSupply: vi.fn(),
  confirmSupply: vi.fn(),
  confirmMany: vi.fn(),
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

vi.mock('../../_shared/services/planningChangeService', () => ({
  listPlanningChangeBatches: vi.fn(),
  getPlanningChangeBatch: vi.fn(),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    // The pending-entity store takes its own countdown toast down once the
    // parked undo settles - without this the store's follow-through timer
    // throws an unhandled rejection if it fires after the test ends.
    dismiss: vi.fn(),
  },
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'user-1', name: 'Test Planner' } },
    status: 'authenticated',
  }),
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pending-1',
  commit_at: '2026-09-18T00:00:10Z',
  entity_id: 'pso-1',
});

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue(null),
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
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import { pendingEntityStore } from '@/lib/pending-entity-store';

const TODAY = '2026-09-17';

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'Test Customer',
    project_sales_order_id: 'pso-1',
    project_line_id: 'pl-1-1',
    line_no: 1,
    item_code: 'ZZT-ITEM-1',
    qty: '10',
    required_date: '2026-09-20',
    fulfilment_location: 'BRW-IB',
    priority: null,
    ...overrides,
  } as BoardDemandLine;
}

type UndoOverlay = {
  revision_no: number;
  refusal: 'linked' | 'actioned' | 'changed' | null;
  decision_id: string;
  /** `PLAN-scm-oi-handover-r2-undo.md` S6. Optional here so the pre-r2 AC-UC-02/03/04
   * fixtures above (written before `mode` existed) still compile - the component's own
   * fallback (`order.undo?.mode ?? 'journal'`) is what a real omitted field would read
   * as too. */
  mode?: 'journal' | 'reconstructed';
};

/** Overlays a mocked `undo` onto `board.orders`, keyed by `sales_order_id` - the same
 * shape `withPendingBatch` in the autobatch spec uses for `pending_change_batch_id`. */
function withUndo(
  board: ReturnType<typeof buildBoard>,
  mapping: Record<string, UndoOverlay | null>,
) {
  return {
    ...board,
    orders: board.orders.map((order) => ({
      ...order,
      undo: mapping[order.sales_order_id] ?? null,
    })),
  } as ReturnType<typeof buildBoard>;
}

function renderPanel(soNumbers: string[]) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} batchId={null} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
}

async function openBoardActions() {
  // Radix's `DropdownMenuTrigger` opens on keyboard activation more reliably than a
  // plain `click` under jsdom - the same pattern `FulfilmentBoardPanel.test.tsx` uses
  // for every other gear-menu interaction in this file's own suite.
  const trigger = await screen.findByRole('button', { name: 'Board actions' });
  fireEvent.keyDown(trigger, { key: 'Enter' });
  await screen.findByRole('menuitem', { name: 'Undo all' });
  return screen.getByRole('menu');
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  // AC-R2-F04 starts an undo whose fixture `commit_at` is already in the
  // past, so the store's own follow-through timer is armed for real; putting
  // it down here (rather than waiting for it to fire on its own after the
  // test ends) is what keeps a later suite from seeing an unhandled
  // rejection from a timer this test left running.
  pendingEntityStore.clear('project_sales_order', 'pso-1');
});

describe('AC-UC-02: one gear entry per undoable order, of three', () => {
  it('lists exactly two entries for two undoable orders, none for the third', async () => {
    const board = buildBoard(
      [
        demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' }),
        demand({ sales_order_id: 'so-2', so_number: 'SO000002', project_sales_order_id: 'pso-2', project_line_id: 'pl-2-1' }),
        demand({ sales_order_id: 'so-3', so_number: 'SO000003', project_sales_order_id: 'pso-3', project_line_id: 'pl-3-1' }),
      ],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 1, refusal: null, decision_id: 'dec-1' },
        'so-2': { revision_no: 1, refusal: null, decision_id: 'dec-2' },
        'so-3': null,
      }),
    );

    renderPanel(['SO000001', 'SO000002', 'SO000003']);
    const menu = await openBoardActions();

    const items = within(menu).getAllByText(/^Undo SO0000\d+ confirm \(rev 1\)$/);
    expect(items).toHaveLength(2);
    expect(within(menu).queryByText(/SO000003/)).not.toBeInTheDocument();
  });
});

describe('AC-UC-03: a refused entry is disabled and states its reason as visible text', () => {
  it('shows "Purchasing linked a PO line" in the item itself, not only as a title', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 1, refusal: 'linked', decision_id: 'dec-1' },
      }),
    );

    renderPanel(['SO000001']);
    const menu = await openBoardActions();

    const item = within(menu).getByText(/Undo SO000001 confirm \(rev 1\)/).closest(
      '[role="menuitem"]',
    ) as HTMLElement;
    expect(item).toHaveAttribute('aria-disabled', 'true');
    // The reason must be readable TEXT inside the item - a `title` attribute is invisible
    // to a screen reader announcing the item and to anyone on a touch device.
    expect(within(item).getByText('Purchasing linked a PO line')).toBeInTheDocument();
  });
});

describe('AC-UC-04: nothing undoable renders no entry and no separator', () => {
  it('renders neither an undo entry nor its separator when no order is undoable', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(withUndo(board, { 'so-1': null }));

    renderPanel(['SO000001']);
    const menu = await openBoardActions();

    expect(within(menu).queryByText(/Undo SO000001 confirm/)).not.toBeInTheDocument();
    const separators = within(menu).queryAllByRole('separator');
    // "Undo all" keeps its own leading separator; no SECOND one is added for an
    // undo-entries block that has nothing to show.
    expect(separators.length).toBeLessThanOrEqual(1);
  });
});

// --------------------------------------------------------------------------- //
// `PLAN-scm-oi-handover-r2-undo.md` S6 - the three FE cases the plan names:
// mode label, `changed` refusal, mode in the parked payload. The panel's own
// `mode`/`RECONSTRUCTED_UNDO_NOTE`/`UNDO_REFUSAL_TITLES.changed` logic already
// shipped in Phase 1 (frontend-first, against `NEXT_PUBLIC_BOARD_UNDO_MOCK`) -
// these pin that contract with a real `undo.mode` on the mocked board payload,
// the same way `AC-UC-02/03/04` above pin the journal-only shape.
// --------------------------------------------------------------------------- //

describe('AC-R2-F02: a reconstructed entry names itself and what it will not restore', () => {
  it('shows ", reconstructed" on the label and the drafts/notes note as its second line', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 3, refusal: null, decision_id: 'dec-1', mode: 'reconstructed' },
      }),
    );

    renderPanel(['SO000001']);
    const menu = await openBoardActions();

    const item = within(menu)
      .getByText('Undo SO000001 confirm (rev 3), reconstructed')
      .closest('[role="menuitem"]') as HTMLElement;
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
    expect(
      within(item).getByText('Saved drafts and row notes are not restored'),
    ).toBeInTheDocument();
  });
});

describe('AC-R2-F03: a "changed" refusal is disabled and states its own reason', () => {
  it('shows "A row changed since this confirm" as visible text in the item', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 1, refusal: 'changed', decision_id: 'dec-1', mode: 'journal' },
      }),
    );

    renderPanel(['SO000001']);
    const menu = await openBoardActions();

    const item = within(menu)
      .getByText(/Undo SO000001 confirm \(rev 1\)/)
      .closest('[role="menuitem"]') as HTMLElement;
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(within(item).getByText('A row changed since this confirm')).toBeInTheDocument();
  });
});

describe('AC-R2-F04 (payload half): mode travels with decision_id in the parked payload', () => {
  it('parks {decision_id, mode} together when a reconstructed entry is pressed', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 2, refusal: null, decision_id: 'dec-9', mode: 'reconstructed' },
      }),
    );

    renderPanel(['SO000001']);
    const menu = await openBoardActions();
    const item = within(menu).getByText('Undo SO000001 confirm (rev 2), reconstructed');
    fireEvent.click(item);

    await waitFor(() => {
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'project_sales_order.undo_confirm',
          payload: { decision_id: 'dec-9', mode: 'reconstructed' },
        }),
      );
    });
  });
});

// --------------------------------------------------------------------------- //
// Review round 1, item 10: the reconstructed label must never be visually
// elided at a desktop viewport - the menu's own width cap (`sm:max-w-80`,
// 20rem) is narrower than "Undo SO000001 confirm (rev 3), reconstructed" plus
// its own second line needs, so the coder must widen it (`sm:max-w-md` or
// wider). Checked at the CSS-class level, since jsdom has no layout engine to
// measure actual visual truncation against.
// --------------------------------------------------------------------------- //

describe('review round: the reconstructed entry is not clipped at desktop width', () => {
  it('does not carry the old sm:max-w-80 cap on the menu content', async () => {
    const board = buildBoard(
      [demand({ sales_order_id: 'so-1', so_number: 'SO000001', project_line_id: 'pl-1-1' })],
      { today: TODAY, freeStock: {}, granularity: 'week' },
    );
    getPlanningBoard.mockResolvedValue(
      withUndo(board, {
        'so-1': { revision_no: 3, refusal: null, decision_id: 'dec-1', mode: 'reconstructed' },
      }),
    );

    renderPanel(['SO000001']);
    const menu = await openBoardActions();

    expect(
      within(menu).getByText('Undo SO000001 confirm (rev 3), reconstructed'),
    ).toBeInTheDocument();
    // `DropdownMenuContent` splits its own passed className onto an INNER
    // `motion.div` (components/ui/dropdown-menu.tsx) - the Radix Content node
    // `role="menu"` resolves to only ever carries the hardcoded `z-50`, so the
    // width cap under test lives on the menu's own first child.
    const contentDiv = menu.firstElementChild as HTMLElement;
    expect(contentDiv.className).not.toMatch(/\bsm:max-w-80\b/);
  });
});
