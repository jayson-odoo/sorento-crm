/**
 * STOCK-STATUS round 6 (owner 06:00, "i think we put this at project quotation also"; OK of mock
 * v6, 18 Oct 07:56; UAC AC-35): the quotation's stock popover shows ONE stock table, the chosen
 * group, the site pools and every other location, with AutoCount's figures and PO qty.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useStockDetailMock = vi.fn();
vi.mock('../../_shared/hooks/useFulfilmentPlanning', () => ({
  useStockDetail: (...args: unknown[]) => useStockDetailMock(...args),
  useStockGroups: () => ({ data: ['IB'] }),
}));

const cellStockTableSpy = vi.fn();
vi.mock('../../fulfilment-planning/components/CellStockTable', () => ({
  CellStockTable: (props: Record<string, unknown>) => {
    cellStockTableSpy(props);
    return <div data-testid="cell-stock-table" />;
  },
}));

const useStockStatusMock = vi.fn<(...args: unknown[]) => Record<string, unknown>>(() => ({ data: undefined as unknown, isLoading: false }));
vi.mock('@/components/stock-status/useStockStatus', () => ({
  useStockStatus: (...args: unknown[]) => useStockStatusMock(...args),
}));

import { QuotationStockChip } from './QuotationStockChip';

const GROUP_ROWS = [{ location: 'BRW-IB', net_of: 'IB' }, { location: 'MWH-IB', net_of: 'IB' }];
const POOL_ROWS = [{ location: 'BRW', net_of: 'pools' }];
const STATUS = { product_id: 'prod-1', locations: [], incoming_pl: [] };

beforeEach(() => {
  vi.clearAllMocks();
  useStockDetailMock.mockImplementation((_p: unknown, _w: unknown, _l: unknown, group: unknown) =>
    group === 'pools'
      ? { data: { locations: POOL_ROWS, incoming: [] }, isLoading: false, isError: false }
      : { data: { locations: GROUP_ROWS, incoming: [], available_qty: '-1988' }, isLoading: false, isError: false },
  );
  useStockStatusMock.mockReturnValue({ data: STATUS, isLoading: false });
});

function openPopover() {
  render(<QuotationStockChip productId="prod-1" group="IB" quantity="2" uom="UNIT" label="SRTWB1515" />);
  fireEvent.click(screen.getByRole('button', { name: 'Stock on SRTWB1515' }));
}

describe('QuotationStockChip popover, round 6', () => {
  it('draws one stock table: the group, then the site pools, with the AutoCount read', () => {
    openPopover();
    expect(screen.getAllByTestId('cell-stock-table')).toHaveLength(1);
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.locations).toEqual([...GROUP_ROWS, ...POOL_ROWS]);
    expect(props.autoCount).toBe(STATUS);
    expect(props.stockOnly).toBe(true);
    expect(useStockStatusMock).toHaveBeenCalledWith('prod-1');
  });

  it("keeps today's figures when the AutoCount read fails", () => {
    useStockStatusMock.mockReturnValue({ data: undefined, isLoading: false });
    openPopover();
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.locations).toEqual([...GROUP_ROWS, ...POOL_ROWS]);
    expect(props.autoCount ?? null).toBeNull();
  });
});
