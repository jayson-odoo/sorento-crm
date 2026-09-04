/**
 * The transfer detail page (`PLAN-scm-cs-planning-uat.md` section E).
 *
 * Header (number, state, the three verbs, prev/next), General and History tabs, and the
 * rule that a `moved` transfer says "Moved, awaiting stock upload" as the STATE and adds
 * no sentence anywhere.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockTransfer } from '../../types/stockTransfer.types';

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
  usePathname: () => '/inventory-management/stock-transfers/tr-1',
  useSearchParams: () =>
    new URLSearchParams('page=1&limit=25&state=proposed&from_warehouse_id=w-brw'),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

// The stock table is the product page's own component and has its own tests; here it only
// has to be rendered, not re-proven.
vi.mock('@/app/(protected)/master-data-management/products/[id]/components/ProductStockTab', () => ({
  default: ({ productId }: { productId: string }) => (
    <div data-testid="product-stock-tab">{productId}</div>
  ),
}));

const getStockTransfer = vi.fn();
const listStockTransfers = vi.fn();
vi.mock('../../services/stockTransferService', () => ({
  getStockTransfer: (...args: unknown[]) => getStockTransfer(...args),
  listStockTransfers: (...args: unknown[]) => listStockTransfers(...args),
  approveStockTransfer: vi.fn(),
  markStockTransferMoved: vi.fn(),
  cancelStockTransfer: vi.fn(),
  bulkApproveStockTransfers: vi.fn(),
}));

import { StockTransferDetail } from './StockTransferDetail';

function transfer(overrides: Partial<StockTransfer> = {}): StockTransfer {
  return {
    id: 'tr-1',
    transfer_no: 'TR-000001',
    state: 'proposed',
    kind: 'own_group',
    qty: '454',
    product_id: 'p-1',
    item_code: 'CWCY605',
    product_name: 'Close coupled WC',
    from_warehouse_id: 'w-dc1-bb',
    from_location: 'DC1-BB',
    to_warehouse_id: 'w-brw-bb',
    to_location: 'BRW-BB',
    sales_order_id: 'so-1',
    so_number: 'SO324132',
    so_line_no: 2,
    project_sales_order_id: 'pso-1',
    customer_name: 'YOTU BUILDER',
    sales_agent_id: 'sa-1',
    agent_code: 'CYNDI',
    agent_name: 'Cyndi Lee',
    supply_decision_id: 'd-1',
    revision_no: 1,
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

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockTransferDetail id="tr-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getStockTransfer.mockResolvedValue(transfer());
  listStockTransfers.mockResolvedValue({
    data: [{ ...transfer(), id: 'tr-1' }, { ...transfer(), id: 'tr-2', transfer_no: 'TR-000002' }],
    pagination: { total: 2, page: 1, limit: 25 },
  });
});

describe('StockTransferDetail - header', () => {
  it('carries the transfer number, the state and the verbs the state allows', async () => {
    renderDetail();

    // Three times, deliberately: the page title, the breadcrumb's leaf (which the
    // title supplies, S5-02) and the record card. Each is the NUMBER rather than
    // the id, because no UUID reaches a screen.
    expect(await screen.findAllByText('TR-000001')).toHaveLength(3);
    expect(
      within(screen.getByRole('navigation', { name: 'breadcrumb' })).getByText('TR-000001'),
    ).toBeInTheDocument();
    expect(screen.getByText('Proposed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark moved' })).toBeNull();
    // Cancel sits behind the gear, not on the header. Radix opens on pointerdown, which
    // jsdom does not synthesise from a click, so the keyboard opens it.
    expect(screen.queryByRole('button', { name: 'Cancel transfer' })).toBeNull();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Stock transfer options' }), { key: 'Enter' });
    expect(await screen.findByRole('menuitem', { name: 'Cancel transfer' })).toBeInTheDocument();
  });

  it('offers prev/next over the same filtered list the reader came from', async () => {
    renderDetail();

    await screen.findAllByText('TR-000001');
    expect(await screen.findByText('1 / 2')).toBeInTheDocument();
    // The filters in the URL are forwarded to the list read, so the chevrons walk the set
    // the reader narrowed to rather than the unfiltered book.
    expect(listStockTransfers).toHaveBeenCalledWith(
      expect.objectContaining({ state: 'proposed', from_warehouse_id: 'w-brw' }),
    );
  });

  it('a moved transfer says so as its state and adds no sentence', async () => {
    getStockTransfer.mockResolvedValue(
      transfer({ state: 'moved', autocount_ref: 'ST-2026/08-0042', moved_at: '2026-08-26T09:00:00' }),
    );
    renderDetail();

    expect(await screen.findByText('Moved, awaiting stock upload')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Stock transfer options' })).toBeNull();
  });
});

describe('StockTransferDetail - tabs', () => {
  it('General names the movement, the SO line and the decision revision', async () => {
    renderDetail();

    expect(await screen.findByText('CWCY605')).toBeInTheDocument();
    expect(screen.getByText('454')).toBeInTheDocument();
    expect(screen.getByText('DC1-BB')).toBeInTheDocument();
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('Use own location')).toBeInTheDocument();
    expect(screen.getByText('SO324132')).toBeInTheDocument();
    expect(screen.getByText('L2')).toBeInTheDocument();
    expect(screen.getByText('YOTU BUILDER')).toBeInTheDocument();
    expect(screen.getByText('Revision 1')).toBeInTheDocument();
    expect(screen.getByTestId('product-stock-tab')).toHaveTextContent('p-1');
  });

  it('History renders every step, with an empty state for the ones not taken', async () => {
    renderDetail();

    await screen.findByText('CWCY605');
    // Radix activates a tab on mousedown, which jsdom does not synthesize from a click.
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'History' }), {
      button: 0,
      ctrlKey: false,
    });

    expect(await screen.findByText('Not approved yet')).toBeInTheDocument();
    expect(screen.getByText('Not moved yet')).toBeInTheDocument();
    expect(screen.getByText('Not cancelled')).toBeInTheDocument();
  });
});

describe('StockTransferDetail - missing record', () => {
  it('says so rather than rendering a blank page', async () => {
    getStockTransfer.mockRejectedValue(new Error('nope'));
    renderDetail();

    expect(await screen.findByText('Stock transfer not found')).toBeInTheDocument();
  });
});
