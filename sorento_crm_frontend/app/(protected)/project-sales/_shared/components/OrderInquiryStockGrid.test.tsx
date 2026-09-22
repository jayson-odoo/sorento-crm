/**
 * `PLAN-oi-request-cs-reserve.md` section 3.9, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-40/AC-RS-41 (Slice 1, S1, FE against the live endpoint).
 *
 * TEST-FIRST (Phase 2): written before `OrderInquiryStockGrid.tsx` exists - a red here is
 * a missing module (the component file itself does not exist yet), never an import typo.
 *
 * `OrderInquiryStockGrid({ productId, location })` is documented (plan 3.9) as a thin
 * wrapper: resolve `group = group_of(location)` client-side (split on the first hyphen -
 * the client twin of `group_of_warehouse_code`), or resolve a BARE pool code to its own
 * `warehouse_id` via the existing warehouse list fetcher, then call `useStockDetail`
 * and render `CellStockTable` with `showGroupSubtotal`.
 *
 * Both `useStockDetail` (`_shared/hooks/useFulfilmentPlanning`) and `CellStockTable`
 * (`fulfilment-planning/components/CellStockTable`) are mocked here - this pins the
 * GRID's own wiring (what it asks for, what it renders with), not the query hook's own
 * network behaviour (covered by `useFulfilmentPlanning.test.tsx`) or the table's own
 * rendering (covered by `CellStockTable.test.tsx`).
 *
 * ASSUMPTION (named for the captain/coder, per the tester's brief): the plan's own words
 * for the bare-pool-code case - "via the existing warehouse select service" - name
 * `_shared/services/warehouseSelectService.ts`, but that service's `fetchWarehouseOptions`
 * keys its options by `warehouse_code` (D17: `stock_location` is a free-text code column
 * with no FK), never by `id` - so it cannot itself hand back the `warehouse_id`
 * `useStockDetail` needs. Whatever the grid actually calls to resolve a bare code to an
 * id has to bottom out at `getWarehouses` (`inventory-management/warehouses/services/
 * warehouseService`), the only warehouse-list fetcher in the codebase that carries `id`
 * on each row - so this suite mocks THAT function directly rather than a wrapper whose
 * name/shape the coder has not written yet. If the coder introduces a dedicated resolver
 * that does not call `getWarehouses` under the hood, this test's second describe block
 * needs updating to mock that resolver instead - flagged rather than guessed twice.
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useStockDetailMock = vi.fn();
vi.mock('../hooks/useFulfilmentPlanning', () => ({
  useStockDetail: (...args: unknown[]) => useStockDetailMock(...args),
}));

const cellStockTableSpy = vi.fn();
vi.mock('../../fulfilment-planning/components/CellStockTable', () => ({
  CellStockTable: (props: Record<string, unknown>) => {
    cellStockTableSpy(props);
    return <div data-testid="cell-stock-table" />;
  },
}));

const getWarehousesMock = vi.fn();
vi.mock('@/app/(protected)/inventory-management/warehouses/services/warehouseService', () => ({
  getWarehouses: (...args: unknown[]) => getWarehousesMock(...args),
}));

import { OrderInquiryStockGrid } from './OrderInquiryStockGrid';

const PRODUCT_ID = 'prod-b2155-nl-blue';

beforeEach(() => {
  vi.clearAllMocks();
  useStockDetailMock.mockReturnValue({
    data: { locations: [] },
    isLoading: false,
    isError: false,
  });
  getWarehousesMock.mockResolvedValue({
    data: [{ id: 'wh-brw-pool', warehouse_code: 'BRW', warehouse_name: 'Batu Rakit Warehouse' }],
  });
});

describe('OrderInquiryStockGrid - AC-RS-41: location resolves to group or warehouse id', () => {
  it('a hyphenated location (BRW-BB) is fetched by GROUP, product by id', async () => {
    render(<OrderInquiryStockGrid productId={PRODUCT_ID} location="BRW-BB" />);

    await waitFor(() => expect(useStockDetailMock).toHaveBeenCalled());
    const [productId, warehouseId, , group] = useStockDetailMock.mock.calls[0];
    expect(productId).toBe(PRODUCT_ID);
    expect(group).toBe('BB');
    // Never the item code string - the plan is explicit ("Product = the row's product id,
    // never the item code string").
    expect(productId).not.toMatch(/BLUE|B2155/i);
  });

  it('a bare pool code (BRW) resolves to that pool warehouse\'s own id, no group', async () => {
    render(<OrderInquiryStockGrid productId={PRODUCT_ID} location="BRW" />);

    await waitFor(() => expect(getWarehousesMock).toHaveBeenCalled());
    await waitFor(() => expect(useStockDetailMock).toHaveBeenCalled());
    const [, warehouseId, , group] = useStockDetailMock.mock.calls[useStockDetailMock.mock.calls.length - 1];
    expect(warehouseId).toBe('wh-brw-pool');
    expect(group == null || group === undefined).toBe(true);
  });
});

describe('OrderInquiryStockGrid - AC-RS-40: renders the shared stock table with the group subtotal', () => {
  it('passes showGroupSubtotal to CellStockTable', async () => {
    render(<OrderInquiryStockGrid productId={PRODUCT_ID} location="BRW-BB" />);

    await screen.findByTestId('cell-stock-table');
    expect(cellStockTableSpy).toHaveBeenCalled();
    const props = cellStockTableSpy.mock.calls[cellStockTableSpy.mock.calls.length - 1][0];
    expect(props.showGroupSubtotal).toBe(true);
  });
});
