/**
 * STOCK-DEBT-LENDABLE (owner, 30 Sep 2026, option B): the cell dialog's three new things.
 *
 * AC-V1 the `order_back` pill ("order back 88"; "short 100 · order back 88" when short
 * outranks), AC-V2 the Covered by wording (a lent on-hand entry says whose stock it was,
 * a lending line lists "Lent to SO... (N)" linking the receiving order), AC-V3 the
 * Rebalance button in the header: disabled with a title when the cell holds no lend,
 * loads the Preview inline when pressed, Confirm posts the preview's own `confirm_body`
 * through the EXISTING `confirmMany` and shows the per-order result, Cancel closes it.
 *
 * Same harness as `StockDebtCellDialog.test.tsx`: the service is mocked, never the
 * component; `useHasPermission` is mocked so the gate (the board's EDIT right) is stated
 * per test.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  StockDebtCell,
  StockDebtDemandLine,
  StockDebtRebalancePreview,
} from '../types/stockDebt.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-debt',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const hasPermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
}));

const getStockDebtCell = vi.fn();
const getStockDebtRebalancePreview = vi.fn();
vi.mock('../services/stockDebtService', () => ({
  getStockDebtList: vi.fn(),
  getStockDebtCell: (...args: unknown[]) => getStockDebtCell(...args),
  getStockDebtRebalancePreview: (...args: unknown[]) => getStockDebtRebalancePreview(...args),
}));

const confirmMany = vi.fn();
vi.mock('../../_shared/services/fulfilmentPlanningService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/fulfilmentPlanningService')
  >();
  return { ...actual, confirmMany: (...args: unknown[]) => confirmMany(...args) };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { StockDebtCellDialog } from './StockDebtCellDialog';

const RECEIVER: StockDebtDemandLine = {
  so_number: 'SO396071',
  agent_code: 'LEENA',
  warehouse_code: 'BRW-BB',
  required_date: '2026-09-01',
  open_qty: 32,
  qty_ordered: 32,
  qty_delivered: 0,
  assigned_qty: 32,
  assigned_source: 'On hand BRW-BB',
  short_qty: 0,
  status: 'covered',
  sales_order_id: 'so-396071',
  lent_qty: 0,
  assigned_from: [
    {
      kind: 'on_hand',
      ref: 'On hand BRW-BB (from SO381065)',
      spo_number: null,
      spo_line_number: null,
      qty: 32,
      lent_from_so_number: 'SO381065',
    },
  ],
};

const LENDER: StockDebtDemandLine = {
  so_number: 'SO381065',
  agent_code: 'LEENA',
  warehouse_code: 'BRW-BB',
  required_date: '2027-03-29',
  open_qty: 88,
  qty_ordered: 88,
  qty_delivered: 0,
  assigned_qty: 0,
  assigned_source: null,
  short_qty: 88,
  status: 'order_back',
  sales_order_id: 'so-381065',
  lent_qty: 88,
  assigned_from: [
    { kind: 'lent', ref: 'Lent to SO396071 (32)', qty: 32, so_number: 'SO396071', sales_order_id: 'so-396071' },
    { kind: 'lent', ref: 'Lent to SO402118 (29)', qty: 29, so_number: 'SO402118', sales_order_id: 'so-402118' },
    { kind: 'lent', ref: 'Lent to SO404890 (27)', qty: 27, so_number: 'SO404890', sales_order_id: 'so-404890' },
  ],
};

const SEP_CELL: StockDebtCell = {
  demand: [RECEIVER],
  supply: [],
  demand_total_qty: 32,
  supply_total_qty: 0,
};

const MAR_CELL: StockDebtCell = {
  demand: [LENDER],
  supply: [],
  demand_total_qty: 88,
  supply_total_qty: 0,
};

const PREVIEW: StockDebtRebalancePreview = {
  lent_qty: 88,
  orders: [
    {
      pso_id: 'pso-396071',
      so_number: 'SO396071',
      agent_code: 'LEENA',
      lines: [
        {
          project_line_id: 'pl-1',
          line_no: 3,
          so_line_no: 3,
          required_date: '2026-09-01',
          open_qty: 32,
          borrow: [
            {
              qty: 32,
              warehouse_code: 'BRW-BB',
              donor_so_number: 'SO381065',
              donor_line_no: 1,
              donor_agent_code: 'LEENA',
              donor_required_date: '2027-03-29',
              reason:
                'Borrow 32 on hand at BRW-BB from SO381065 line 1 (LEENA, due 29 Mar 2027); its debt lands in Mar 2027',
            },
          ],
          buy_qty: 0,
        },
      ],
      order_backs: [
        { donor_so_number: 'SO381065', donor_line_no: 1, qty: 32, required_date: '2027-03-29' },
      ],
    },
    {
      pso_id: 'pso-404890',
      so_number: 'SO404890',
      agent_code: 'LEENA',
      lines: [
        {
          project_line_id: 'pl-2',
          line_no: 5,
          so_line_no: 5,
          required_date: '2026-12-03',
          open_qty: 207,
          borrow: [
            {
              qty: 27,
              warehouse_code: 'BRW-BB',
              donor_so_number: 'SO381065',
              donor_line_no: 1,
              donor_agent_code: 'LEENA',
              donor_required_date: '2027-03-29',
              reason:
                'Borrow 27 on hand at BRW-BB from SO381065 line 1 (LEENA, due 29 Mar 2027); its debt lands in Mar 2027',
            },
          ],
          buy_qty: 180,
        },
      ],
      order_backs: [
        { donor_so_number: 'SO381065', donor_line_no: 1, qty: 27, required_date: '2027-03-29' },
      ],
    },
  ],
  skipped: [
    { so_number: 'SO405511', qty: 14, reason: 'Not adopted onto fulfilment planning yet; adopt it on the board first.' },
  ],
  confirm_body: {
    orders: [
      { pso_id: 'pso-396071', lines: [{ project_line_id: 'pl-1' }] },
      { pso_id: 'pso-404890', lines: [{ project_line_id: 'pl-2' }] },
    ],
  },
};

function renderDialog(cell: StockDebtCell, month = '2026-09', balance = -44) {
  getStockDebtCell.mockResolvedValue(cell);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockDebtCellDialog
        productId="p1"
        productCode="SRTSS8710"
        productName="Stainless steel sink 871"
        month={month}
        monthLabel="Sep 26"
        balance={balance}
        book="project"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  hasPermission.mockReturnValue(true);
});

describe('StockDebtCellDialog, lendable landed pins', () => {
  it('AC-V1: a lending line reads "order back N" in its own pill', async () => {
    renderDialog(MAR_CELL, '2027-03', -88);
    const row = (await screen.findByText('SO381065')).closest('tr') as HTMLElement;
    const pill = within(row).getByText('order back 88');
    expect(pill.className).toMatch(/violet/);
    expect(within(row).queryByText('short 88')).not.toBeInTheDocument();
  });

  it('AC-V1: short outranks, and the lend is still said', async () => {
    renderDialog(
      { ...MAR_CELL, demand: [{ ...LENDER, open_qty: 100, short_qty: 100, status: 'short' }] },
      '2027-03',
      -100,
    );
    const row = (await screen.findByText('SO381065')).closest('tr') as HTMLElement;
    expect(within(row).getByText('short 100')).toBeInTheDocument();
    expect(within(row).getByText('order back 88')).toBeInTheDocument();
  });

  it('AC-V2: a receiving line names whose stock it holds', async () => {
    renderDialog(SEP_CELL);
    const row = (await screen.findByText('SO396071')).closest('tr') as HTMLElement;
    expect(within(row).getByText('On hand BRW-BB (from SO381065)')).toBeInTheDocument();
    expect(within(row).getByText('covered')).toBeInTheDocument();
  });

  it('AC-V2: a lending line lists every receiver, linking the receiving order', async () => {
    renderDialog(MAR_CELL, '2027-03', -88);
    const row = (await screen.findByText('SO381065')).closest('tr') as HTMLElement;
    const link = within(row).getByRole('link', { name: 'Lent to SO396071 (32)' });
    expect(link).toHaveAttribute('href', '/scm/sales-orders/so-396071');
    expect(within(row).getByText('Lent to SO402118 (29)')).toBeInTheDocument();
    expect(within(row).getByText('Lent to SO404890 (27)')).toBeInTheDocument();
  });

  it('AC-V3: Rebalance is disabled, with a title, when the cell holds no lend', async () => {
    renderDialog({
      ...SEP_CELL,
      demand: [{ ...RECEIVER, assigned_from: [{ kind: 'on_hand', ref: 'On hand BRW-BB', spo_number: null, spo_line_number: null, qty: 32, lent_from_so_number: null }] }],
    });
    await screen.findByText('SO396071');
    const button = screen.getByRole('button', { name: 'Rebalance' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Nothing to rebalance in this cell');
    expect(getStockDebtRebalancePreview).not.toHaveBeenCalled();
  });

  it('AC-V3: Rebalance is not offered without the fulfilment board\'s edit right', async () => {
    hasPermission.mockReturnValue(false);
    renderDialog(SEP_CELL);
    await screen.findByText('SO396071');
    expect(screen.queryByRole('button', { name: 'Rebalance' })).not.toBeInTheDocument();
    expect(hasPermission).toHaveBeenCalledWith('projects.projects.edit');
  });

  it('AC-V3: pressing Rebalance loads the Preview inline, Cancel closes it', async () => {
    getStockDebtRebalancePreview.mockResolvedValue(PREVIEW);
    renderDialog(SEP_CELL);
    await screen.findByText('SO396071');

    fireEvent.click(screen.getByRole('button', { name: 'Rebalance' }));
    await waitFor(() =>
      expect(getStockDebtRebalancePreview).toHaveBeenCalledWith('p1', 'project'),
    );
    expect(
      await screen.findByText('Rebalance preview · 2 sales orders, 88 units from SO381065'),
    ).toBeInTheDocument();
    expect(screen.getByText('SO396071 line 3 · LEENA · due 01/09/2026')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Borrow 32 on hand at BRW-BB from SO381065 line 1 (LEENA, due 29 Mar 2027); its debt lands in Mar 2027',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('32 for SO381065 line 1 at 29/03/2027')).toBeInTheDocument();
    // The split line says how much is bought.
    expect(screen.getByText(/180: only 27 of 207 can be covered from stock/)).toBeInTheDocument();
    // The receiver that is not adopted is named with the reason.
    expect(screen.getByText(/SO405511 \(14 lent\)/)).toBeInTheDocument();
    // The trigger greys out while the preview is open.
    expect(screen.getByRole('button', { name: 'Rebalance' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText(/Rebalance preview/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rebalance' })).not.toBeDisabled();
  });

  it('AC-V3: Confirm posts the preview\'s own confirm_body and shows the per-order result', async () => {
    getStockDebtRebalancePreview.mockResolvedValue(PREVIEW);
    confirmMany.mockResolvedValue({
      results: [
        { pso_id: 'pso-396071', ok: true, decision_revision: 4, inquiry_rows_created: 1 },
        { pso_id: 'pso-404890', ok: false, error: 'SO381065 line 1 is no longer open demand, so it cannot be borrowed from.' },
      ],
    });
    renderDialog(SEP_CELL);
    await screen.findByText('SO396071');
    fireEvent.click(screen.getByRole('button', { name: 'Rebalance' }));
    await screen.findByText(/Rebalance preview/);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 2 orders' }));
    await waitFor(() => expect(confirmMany).toHaveBeenCalledWith(PREVIEW.confirm_body));

    expect(await screen.findByText('Rebalanced 1 of 2 sales orders')).toBeInTheDocument();
    expect(screen.getByText('SO396071 revision 4')).toBeInTheDocument();
    expect(
      screen.getByText(/SO404890: SO381065 line 1 is no longer open demand/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Rebalance preview/)).not.toBeInTheDocument();
    // The cell is read again after the press.
    await waitFor(() => expect(getStockDebtCell).toHaveBeenCalledTimes(2));
  });
});
