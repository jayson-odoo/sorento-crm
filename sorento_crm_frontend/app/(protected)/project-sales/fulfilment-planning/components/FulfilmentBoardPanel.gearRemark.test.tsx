/**
 * OI-SPLIT-GUIDE F26: the board's own "Split delivery" dialog (the REAL LineSplitDialog, opened
 * from the gear) treats an unsplit line with a saved decision draft like the guide does: the
 * remark cell's default is the contribution's `saved_remark`, and a typed remark is saved as the
 * draft decision `remark` (putLineDraft), never as a one-row split. A line with no saved decision
 * keeps today's behaviour.
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



vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import { wireLine, wireSplit } from '@/test-mocks/lineSplitSheetKit';

const TODAY = '2026-09-17';
const DECISION = {
  revision_no: 3,
  confirmed_at: '2026-09-16T02:00:00',
  timely_spo_qty: '0',
  reserve: [],
  borrow: [],
  buy_qty: '10',
};
function demand(no: number, item: string): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    customer_name: 'Test Customer',
    project_sales_order_id: 'pso-so-1',
    project_line_id: `pl-1-${no}`,
    line_no: no,
    item_code: item,
    qty: '10',
    required_date: '2026-09-20',
    fulfilment_location: 'BRW-IB',
    priority: null,
    decision: DECISION,
  } as BoardDemandLine;
}

type Board = ReturnType<typeof buildBoard>;
function board() {
  const b = buildBoard([demand(3, 'ZZT-ITEM-3'), demand(4, 'ZZT-ITEM-4')], {
    today: TODAY, freeStock: {}, granularity: 'week',
  });
  const apply = (entry: Record<string, unknown>) =>
    entry.project_line_id === 'pl-1-3'
      ? {
          ...entry,
          saved_remark: 'USE BRW 522 & ORDER 294',
          draft: { decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-09-08T00:00:00Z' },
        }
      : entry;
  return {
    ...b,
    cells: b.cells.map((c) => ({ ...c, contributions: c.contributions.map((x) => apply(x as never)) })),
    contributions: (b as unknown as { contributions: unknown[] }).contributions.map((x) => apply(x as never)),
  } as unknown as Board;
}

const READ = () => ({
  pso_id: 'pso-so-1', so_number: 'SO000001', so_date: '2026-09-03', customer: 'C', project: 'P', confirmed_at: null,
  lines: [3, 4].map((no) =>
    wireLine(no, `ZZT-ITEM-${no}`, 10, '2026-09-20', { line_id: `pl-1-${no}`, now_qty: 10, split_state: 'applied' }),
  ),
});

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockImplementation(() => Promise.resolve(READ()));
  saveLineSplits.mockImplementation(() => Promise.resolve(READ()));
  putLineDraft.mockResolvedValue({ decision: { verdict: 'approved' }, saved_by: 'Test Planner', saved_at: '2026-09-03T00:00:00Z' });
});

async function openGearDialog() {
  const b = board();
  getPlanningBoard.mockResolvedValue(b);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={['SO000001']} batchId={null} onBack={vi.fn()} />
    </QueryClientProvider>,
  );
  await screen.findByTestId('fulfilment-board-matrix');
  const trigger = await screen.findByRole('button', { name: 'Board actions' });
  fireEvent.keyDown(trigger, { key: 'Enter' });
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Split delivery SO000001' }));
  await screen.findByLabelText('Remark, line 3');
  return (b as unknown as { contributions: { key: string; project_line_id: string }[] }).contributions;
}

describe('F26: the board dialog and an unsplit saved line\'s remark', () => {
  it('the remark cell\'s default VALUE is the line\'s saved_remark; a line with no saved decision starts empty', async () => {
    await openGearDialog();
    expect((screen.getByLabelText('Remark, line 3') as HTMLInputElement).value).toBe('USE BRW 522 & ORDER 294');
    expect((screen.getByLabelText('Remark, line 4') as HTMLInputElement).value).toBe('');
  });

  it('typing a remark on the saved line and Save stores it as the draft decision remark and sends NO one-row split for it', async () => {
    const contributions = await openGearDialog();
    const key = contributions.find((c) => c.project_line_id === 'pl-1-3')!.key;
    fireEvent.change(screen.getByLabelText('Remark, line 3'), { target: { value: 'ORDER BACK URGENT' } });
    const save = screen.getByRole('button', { name: /^save$/i });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(putLineDraft).toHaveBeenCalled());
    const [draftKey, decision] = putLineDraft.mock.calls[0];
    expect(draftKey).toBe(key);
    expect(decision.remark).toBe('ORDER BACK URGENT');
    for (const [, body] of saveLineSplits.mock.calls) {
      const l3 = body.lines.find((l: { line_id: string }) => l.line_id === 'pl-1-3');
      if (l3) expect(l3.splits).toHaveLength(0);
    }
  });

  it('pin: a line WITHOUT a saved decision keeps today\'s behaviour (a typed remark is a one-row split, no draft write)', async () => {
    await openGearDialog();
    fireEvent.change(screen.getByLabelText('Remark, line 4'), { target: { value: 'SITE HOLD' } });
    const save = screen.getByRole('button', { name: /^save$/i });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const l4 = saveLineSplits.mock.calls[0][1].lines.find((l: { line_id: string }) => l.line_id === 'pl-1-4');
    expect(l4.splits).toHaveLength(1);
    expect(l4.splits[0].remark).toBe('SITE HOLD');
    expect(putLineDraft).not.toHaveBeenCalled();
  });
});

/**
 * OI-SPLIT-GEAR-REMARK H1-H5: line 4 has NO draft; its active revision froze a confirmed remark.
 */
describe('OI-SPLIT-GEAR-REMARK: a no-draft line\'s confirmed remark in the gear Split delivery sheet', () => {
  const withConfirmed = (confirmed: string | null) => {
    const b = board();
    const apply = (entry: Record<string, unknown>) =>
      entry.project_line_id === 'pl-1-4' ? { ...entry, confirmed_remark: confirmed, saved_remark: 'DEFAULT WORDS' } : entry;
    return {
      ...b,
      cells: b.cells.map((c) => ({ ...c, contributions: c.contributions.map((x) => apply(x as never)) })),
      contributions: (b as unknown as { contributions: unknown[] }).contributions.map((x) => apply(x as never)),
    } as unknown as Board;
  };
  async function open(confirmed: string | null, storedSplitRemark?: string) {
    const b = withConfirmed(confirmed);
    getPlanningBoard.mockResolvedValue(b);
    const read = () => ({
      ...READ(),
      lines: READ().lines.map((l) =>
        storedSplitRemark !== undefined && l.line_id === 'pl-1-4'
          ? { ...l, splits: [wireSplit('s-4', 10, '2026-09-20', 'pl-1-4', { remark: storedSplitRemark })] }
          : l,
      ),
    });
    getLineSplits.mockImplementation(() => Promise.resolve(read()));
    saveLineSplits.mockImplementation(() => Promise.resolve(read()));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <FulfilmentBoardPanel soNumbers={['SO000001']} batchId={null} onBack={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByTestId('fulfilment-board-matrix');
    const trigger = await screen.findByRole('button', { name: 'Board actions' });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Split delivery SO000001' }));
    await screen.findByLabelText('Remark, line 4');
  }
  const box4 = () => screen.getByLabelText('Remark, line 4') as HTMLInputElement;
  const row4 = () => screen.getByLabelText('Remark, line 4').closest('[data-testid="split-line-4"]') as HTMLElement;

  it('H1: shows the confirmed remark X with the edited marker, not the default words', async () => {
    await open('X CONFIRMED');
    expect(box4().value).toBe('X CONFIRMED');
    expect(within(row4()).getByText('edited')).toBeInTheDocument();
  });

  it('H2: Save with nothing changed writes no split remark and no draft for the line', async () => {
    await open('X CONFIRMED');
    const save = screen.getByRole('button', { name: /^save$/i });
    if (!(save as HTMLButtonElement).disabled) fireEvent.click(save);
    await new Promise((r) => setTimeout(r, 50));
    for (const [, body] of saveLineSplits.mock.calls) {
      const l4 = body.lines.find((l: { line_id: string }) => l.line_id === 'pl-1-4');
      for (const sp of l4?.splits ?? []) expect(sp.remark ?? '').not.toBe('X CONFIRMED');
    }
    expect(putLineDraft).not.toHaveBeenCalled();
  });

  it('H3: a split remark already stored on the line wins over the confirmed remark', async () => {
    await open('X CONFIRMED', 'Y STORED');
    expect(box4().value).toBe('Y STORED');
  });

  it('H4: a typed remark is stored as the line split remark (no draft); emptying it shows X again on blur', async () => {
    await open('X CONFIRMED');
    fireEvent.change(box4(), { target: { value: 'Z TYPED' } });
    const save = screen.getByRole('button', { name: /^save$/i });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const l4 = saveLineSplits.mock.calls[0][1].lines.find((l: { line_id: string }) => l.line_id === 'pl-1-4');
    expect(l4.splits).toHaveLength(1);
    expect(l4.splits[0].remark).toBe('Z TYPED');
    expect(putLineDraft).not.toHaveBeenCalled();
  });

  it('H4: emptying the box and blurring shows X again', async () => {
    await open('X CONFIRMED');
    fireEvent.change(box4(), { target: { value: 'Z TYPED' } });
    fireEvent.change(box4(), { target: { value: '' } });
    fireEvent.blur(box4());
    await waitFor(() => expect(box4().value).toBe('X CONFIRMED'));
  });

  it('H5 pin: a no-draft line with no confirmed remark keeps the default words and no marker', async () => {
    await open(null);
    expect(box4().value).toBe('');
    expect(within(row4()).queryByText('edited')).not.toBeInTheDocument();
  });
});
