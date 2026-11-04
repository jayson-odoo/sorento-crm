/**
 * OI-RESERVE-USED-ROW, owner hand test (4 Nov): the snapshot drill reuses the grids' column
 * visibility controller (`DataGridColumnVisibility`), ONE setting for every OI table in the
 * dialog, saved per user through the grids' own store (`useListingColumnPreferences` over
 * `listColumnPreferencesService`, listing key `projects.stock_debt.view::snapshot-drill`).
 *
 * The real preference hook runs; only its service is mocked at the boundary.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const KEY = 'projects.stock_debt.view::snapshot-drill';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-debt/snapshots/s1',
  useSearchParams: () => new URLSearchParams(''),
}));
const getConfig = vi.fn();
const upsertConfig = vi.fn();
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...args: unknown[]) => getConfig(...args),
  upsertUserListColumnConfig: (...args: unknown[]) => upsertConfig(...args),
  resetUserListColumnConfig: vi.fn(),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));
vi.mock('../../_shared/hooks/useOrderInquiry', () => ({
  useOrderInquiryHeaderLines: () => ({ data: [] }),
}));

const oiRow = (oi: string, no: string) => ({
  oi_id: oi, inquiry_no: no, row_id: `row-${oi}`, qty: 33, delivery_date: '2027-05-04',
  stock_location: 'BRW-BB', verb: 'ORDER', state: 'raised', now_state: 'raised',
  reserve_state: null, remaining: 33, requestable: false,
});
const line = (so: string, oi: string, no: string) => ({
  so_number: so, sales_order_id: `id-${so}`, sales_order_line_id: `line-${so}`,
  customer_name: 'ZZT CUSTOMER', project_label: 'ZZT SITE', agent_code: 'AG',
  warehouse_code: 'BRW-BB', required_date: '2027-05-04', bucket: '2027-05', qty_ordered: 33,
  qty_delivered: 0, open_qty: 33, assigned_qty: 0, assigned_source: null, assigned_from: [],
  status: 'short', short_qty: 33, oi_rows: [oiRow(oi, no)], now: { so_status: 'open', open_qty: 33 },
});
vi.mock('../hooks/useStockDebtSnapshots', () => ({
  SNAPSHOTS_KEY: ['snapshots'],
  useSnapshotLinesQuery: () => ({
    data: { lines: [line('SO396347', 'oi-1', 'OI-2609-0257'), line('SO400001', 'oi-2', 'OI-2609-0501')] },
    isLoading: false,
    isError: false,
  }),
}));

import { SnapshotDrillDialog } from './SnapshotDrillDialog';

const ROW = {
  row_id: 'r1', product_id: 'p1', product_code: 'SRTSA830-PJ', product_name: null, months: [],
  tba: 0, undated: 0, unlocated: 0, total: -66, supplier_id: null, supplier_name: null,
  category_code: null, pool_on_hand: 0, pool_po_qty: 0, pool_incoming_qty: 0,
  dealer_outstanding: 0, decision: null, decision_warehouse_id: null,
};

function renderDrill(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={client}>
      <SnapshotDrillDialog
        snapshotId="s1"
        row={ROW as never}
        month={null}
        label="all months"
        takenAt="2026-10-26T08:55:00Z"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

function customerHeaders() {
  return screen.queryAllByRole('columnheader', { name: /Customer/ });
}

beforeEach(() => {
  getConfig.mockReset();
  upsertConfig.mockReset();
  upsertConfig.mockResolvedValue({ listing_key: KEY, config: {} });
});

describe('snapshot drill: one column layout per user for every OI table', () => {
  it('each OI table offers the shared Columns menu naming the columns as their headers do', async () => {
    getConfig.mockResolvedValue({ listing_key: KEY, config: null });
    const user = userEvent.setup();
    renderDrill();
    const buttons = await screen.findAllByRole('button', { name: 'Columns' });
    expect(buttons).toHaveLength(2);
    await user.click(buttons[0]);
    const menu = await screen.findByRole('menu');
    for (const name of ['Customer', 'Covered by', 'Short', 'OI row', 'Now']) {
      expect(within(menu).getByRole('menuitemcheckbox', { name })).toBeInTheDocument();
    }
  });

  it('hiding a column in one table hides it in every table and saves it under the drill key', async () => {
    getConfig.mockResolvedValue({ listing_key: KEY, config: null });
    const user = userEvent.setup();
    renderDrill();
    await waitFor(() => expect(customerHeaders()).toHaveLength(2));

    const buttons = await screen.findAllByRole('button', { name: 'Columns' });
    await user.click(buttons[1]);
    await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Customer' }));

    await waitFor(() => expect(customerHeaders()).toHaveLength(0));
    await waitFor(
      () =>
        expect(upsertConfig).toHaveBeenCalledWith(
          KEY,
          expect.objectContaining({
            columnVisibility: expect.objectContaining({ customer_name: false }),
          }),
        ),
      { timeout: 3000 },
    );
    expect(getConfig).toHaveBeenCalledWith(KEY);
  });

  it('restores the saved layout when it arrives after the tables mounted (a real network read)', async () => {
    // Browser pass: with a slow read, the tables' empty defaults were synced first and then
    // pushed back over the saved layout once it applied, so Customer reappeared on reload.
    getConfig.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve({ listing_key: KEY, config: { columnVisibility: { customer_name: false } } }),
            150,
          ),
        ),
    );
    renderDrill();
    await screen.findAllByRole('button', { name: 'Columns' });
    await waitFor(() => expect(customerHeaders()).toHaveLength(0), { timeout: 2000 });
    // And it stays hidden: nothing syncs the defaults back afterwards.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(customerHeaders()).toHaveLength(0);
    expect(screen.getAllByRole('columnheader', { name: /Project/ })).toHaveLength(2);
  });

  it('keeps a hidden column hidden when the drill is closed and opened again in the same session', async () => {
    // Browser pass: the saved layout came from the query cache on reopen, applied in the same
    // commit as the tables' empty defaults, and the defaults were pushed back over it (and saved).
    getConfig.mockResolvedValue({ listing_key: KEY, config: null });
    upsertConfig.mockImplementation((key: string, payload: unknown) =>
      Promise.resolve({ listing_key: key, config: payload }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    const first = renderDrill(client);
    const buttons = await screen.findAllByRole('button', { name: 'Columns' });
    await user.click(buttons[0]);
    await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Customer' }));
    await waitFor(() => expect(upsertConfig).toHaveBeenCalled(), { timeout: 3000 });
    first.unmount();
    upsertConfig.mockClear();

    renderDrill(client);
    await screen.findAllByRole('button', { name: 'Columns' });
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(customerHeaders()).toHaveLength(0);
    // Nothing wrote Customer back to visible.
    for (const [, payload] of upsertConfig.mock.calls) {
      expect((payload as { columnVisibility?: Record<string, boolean> }).columnVisibility?.customer_name).not.toBe(true);
    }
  });

  it('restores the saved layout on open, in every table', async () => {
    getConfig.mockResolvedValue({
      listing_key: KEY,
      config: { columnVisibility: { customer_name: false, now: false } },
    });
    renderDrill();
    await screen.findAllByRole('button', { name: 'Columns' });
    await waitFor(() => expect(customerHeaders()).toHaveLength(0));
    expect(screen.queryAllByRole('columnheader', { name: /^Now/ })).toHaveLength(0);
    expect(screen.getAllByRole('columnheader', { name: /Project/ })).toHaveLength(2);
  });
});
