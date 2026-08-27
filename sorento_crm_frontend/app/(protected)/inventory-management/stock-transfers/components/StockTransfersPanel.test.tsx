/**
 * The Transfers grid (`PLAN-scm-cs-planning-uat.md` section E, AC-E5/AC-E6).
 *
 * Columns, row actions, the three dialogs, bulk approve and the empty state - plus the
 * pinned mode the SO and sales-agent detail tabs use, which must ask the service for that
 * order/agent and drop the filter bar.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockTransfer } from '../types/stockTransfer.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/inventory-management/stock-transfers',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/app/(protected)/inventory-management/warehouses/services/warehouseService', () => ({
  getWarehouses: vi.fn().mockResolvedValue({ data: [] }),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: vi.fn().mockResolvedValue([]),
}));

const listStockTransfers = vi.fn();
const approveStockTransfer = vi.fn();
const markStockTransferMoved = vi.fn();
const cancelStockTransfer = vi.fn();
const bulkApproveStockTransfers = vi.fn();
vi.mock('../services/stockTransferService', () => ({
  listStockTransfers: (...args: unknown[]) => listStockTransfers(...args),
  getStockTransfer: vi.fn(),
  approveStockTransfer: (...args: unknown[]) => approveStockTransfer(...args),
  markStockTransferMoved: (...args: unknown[]) => markStockTransferMoved(...args),
  cancelStockTransfer: (...args: unknown[]) => cancelStockTransfer(...args),
  bulkApproveStockTransfers: (...args: unknown[]) => bulkApproveStockTransfers(...args),
}));

import { StockTransfersPanel } from './StockTransfersPanel';

function transfer(overrides: Partial<StockTransfer> = {}): StockTransfer {
  return {
    id: 'tr-1',
    transfer_no: 'TR-000001',
    state: 'proposed',
    kind: 'pool',
    qty: '71',
    product_id: 'p-1',
    item_code: 'SRT382-6-DIY',
    product_name: 'Basin',
    from_warehouse_id: 'w-brw',
    from_location: 'BRW',
    to_warehouse_id: 'w-brw-bb',
    to_location: 'BRW-BB',
    sales_order_id: 'so-1',
    so_number: 'SO415472',
    so_line_no: 1,
    project_sales_order_id: 'pso-1',
    customer_name: 'YOTU BUILDER',
    sales_agent_id: 'sa-1',
    agent_code: 'CYNDI',
    agent_name: 'Cyndi Lee',
    supply_decision_id: 'd-1',
    revision_no: 2,
    proposed_at: '2026-08-25T08:42:00',
    approved_by: null,
    approved_by_name: null,
    approved_at: null,
    moved_by: null,
    moved_by_name: null,
    moved_at: null,
    cancelled_by: null,
    cancelled_by_name: null,
    cancelled_at: null,
    cancelled_reason: null,
    autocount_ref: null,
    created_at: '2026-08-25T08:42:00',
    updated_at: '2026-08-25T08:42:00',
    ...overrides,
  };
}

/**
 * The row actions live behind the `⋯` menu, so open it before clicking one.
 * Radix opens on pointerdown, which jsdom does not synthesize from a click, so drive it by
 * keyboard instead (ArrowDown opens and focuses the first item).
 */
async function openRowMenu(transferNo = 'TR-000001') {
  const trigger = await screen.findByRole('button', { name: `Actions for ${transferNo}` });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menu');
}

function envelope(rows: StockTransfer[]) {
  return { data: rows, pagination: { total: rows.length, page: 1, limit: 25 }, empty: !rows.length };
}

function renderPanel(props: Partial<React.ComponentProps<typeof StockTransfersPanel>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockTransfersPanel listingKey="inventory.stock_transfers.view" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listStockTransfers.mockResolvedValue(envelope([transfer()]));
});

describe('StockTransfersPanel - rows', () => {
  it('says what moves, from where to where, for which order', async () => {
    renderPanel();

    expect(await screen.findByText('TR-000001')).toBeInTheDocument();
    expect(screen.getByText('SRT382-6-DIY')).toBeInTheDocument();
    expect(screen.getByText('71 BRW -> BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('Use shared stock')).toBeInTheDocument();
    expect(screen.getByText('SO415472 L1')).toBeInTheDocument();
    expect(screen.getByText('YOTU BUILDER')).toBeInTheDocument();
    expect(
      screen.getAllByText('Proposed').find((el) => el.closest('[data-slot="badge"]')),
    ).toBeDefined();
  });

  it('a moved transfer reads "Moved, awaiting stock upload" and nothing more', async () => {
    listStockTransfers.mockResolvedValue(
      envelope([transfer({ state: 'moved', autocount_ref: 'ST-2026/08-0042' })]),
    );
    renderPanel();

    expect(await screen.findByText('Moved, awaiting stock upload')).toBeInTheDocument();
  });

  it('opens the transfer on row click, carrying the filtered list into the URL', async () => {
    renderPanel({ salesOrderId: 'so-1' });
    const row = (await screen.findByText('TR-000001')).closest('tr');

    fireEvent.click(row as HTMLElement);

    const href = push.mock.calls[0][0] as string;
    expect(href).toContain('/inventory-management/stock-transfers/tr-1');
    // The pager on the detail page walks the SAME set, so the filters ride along.
    expect(href).toContain('sales_order_id=so-1');
    expect(href).toContain('sort=proposed_at');
  });
});

describe('StockTransfersPanel - row actions', () => {
  it('offers Approve and Cancel on a proposed transfer, never Mark moved', async () => {
    renderPanel();
    const menu = await openRowMenu();

    expect(within(menu).getByRole('menuitem', { name: 'Approve' })).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Cancel' })).toBeInTheDocument();
    expect(within(menu).queryByRole('menuitem', { name: 'Mark moved' })).toBeNull();
  });

  it('offers Cancel alone on an approved transfer - Mark moved is not a press here (the captain, 27 Aug)', async () => {
    listStockTransfers.mockResolvedValue(envelope([transfer({ state: 'approved' })]));
    renderPanel();
    const menu = await openRowMenu();

    expect(within(menu).queryByRole('menuitem', { name: 'Mark moved' })).toBeNull();
    expect(within(menu).queryByRole('menuitem', { name: 'Approve' })).toBeNull();
  });

  it('offers nothing on a cancelled transfer', async () => {
    listStockTransfers.mockResolvedValue(envelope([transfer({ state: 'cancelled' })]));
    renderPanel();

    await screen.findByText('TR-000001');
    expect(screen.queryByRole('button', { name: 'Actions for TR-000001' })).toBeNull();
  });

  it('confirms before approving, and only then posts', async () => {
    approveStockTransfer.mockResolvedValue(transfer({ state: 'approved' }));
    renderPanel();
    const menu = await openRowMenu();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Approve' }));

    expect(await screen.findByText('Approve TR-000001?')).toBeInTheDocument();
    expect(approveStockTransfer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(approveStockTransfer).toHaveBeenCalledWith('tr-1'));
  });

  it('asks for a reason before cancelling', async () => {
    cancelStockTransfer.mockResolvedValue(transfer({ state: 'cancelled' }));
    renderPanel();
    const menu = await openRowMenu();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Cancel' }));

    expect(await screen.findByText('Cancel TR-000001?')).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Cancel transfer' });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Customer collected it' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel transfer' }));

    await waitFor(() =>
      expect(cancelStockTransfer).toHaveBeenCalledWith('tr-1', 'Customer collected it'),
    );
  });
});

describe('StockTransfersPanel - bulk approve', () => {
  it('confirms with the count before approving the selection', async () => {
    bulkApproveStockTransfers.mockResolvedValue({ approved: 1, skipped: [] });
    renderPanel();

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TR-000001' }));
    fireEvent.click(await screen.findByRole('button', { name: /Approve/ }));

    // The bulk verb confirms first, exactly like the single one, and the copy says how many.
    expect(await screen.findByText('Approve 1 transfer?')).toBeInTheDocument();
    expect(bulkApproveStockTransfers).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(bulkApproveStockTransfers).toHaveBeenCalledWith(['tr-1']));
  });

  it('drops the selection when the set under it changes, and submits only this page', async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select TR-000001' }));
    expect(screen.getByRole('checkbox', { name: 'Select TR-000001' })).toBeChecked();

    // Re-sorting reorders the set under the tick (the search box is hidden while the bulk
    // strip is up, so the sort is the reachable one of the five triggers). A tick made
    // against the old order must not survive it, or Approve would act on rows nobody
    // deliberately chose.
    fireEvent.click(screen.getByRole('button', { name: 'Transfer' }));

    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: 'Select TR-000001' })).not.toBeChecked(),
    );
    await waitFor(() =>
      expect(listStockTransfers).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'transfer_no' }),
      ),
    );
  });
});

describe('StockTransfersPanel - pinned to one record', () => {
  it('asks for that sales order only and drops the filter bar', async () => {
    renderPanel({ salesOrderId: 'so-1', showFilters: false });

    await screen.findByText('TR-000001');
    expect(listStockTransfers).toHaveBeenCalledWith(
      expect.objectContaining({ sales_order_id: 'so-1' }),
    );
    expect(screen.queryByRole('checkbox', { name: 'Select TR-000001' })).toBeNull();
  });

  it('asks for that sales agent only', async () => {
    renderPanel({ salesAgentId: 'sa-1', showFilters: false });

    await screen.findByText('TR-000001');
    expect(listStockTransfers).toHaveBeenCalledWith(
      expect.objectContaining({ sales_agent_id: 'sa-1' }),
    );
  });
});

describe('StockTransfersPanel - empty state', () => {
  it('names where a transfer is born', async () => {
    listStockTransfers.mockResolvedValue(envelope([]));
    renderPanel();

    expect(await screen.findByText('No stock transfers yet')).toBeInTheDocument();
    expect(
      screen.getByText('Confirming supply from another location raises the movement here.'),
    ).toBeInTheDocument();
  });
});
