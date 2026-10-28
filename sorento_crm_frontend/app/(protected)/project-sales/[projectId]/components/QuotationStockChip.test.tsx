/**
 * STOCK-STATUS round 6 (owner 06:00, "i think we put this at project quotation also"; OK of mock
 * v6, 18 Oct 07:56; UAC AC-35): the quotation's stock popover shows ONE stock table, the chosen
 * group, the site pools and every other location, with AutoCount's figures and PO qty.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useQuotationLineStockMock = vi.fn();
const useStockDetailMock = vi.fn();
vi.mock('../../_shared/hooks/useFulfilmentPlanning', () => ({
  useQuotationLineStock: (...args: unknown[]) => useQuotationLineStockMock(...args),
  // Kept only to prove the chip no longer asks for a group or pool read.
  useStockDetail: (...args: unknown[]) => useStockDetailMock(...args),
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

const row = (location: string, onHand: string, so = '0', spo = '0') => ({
  location,
  qty_on_hand: onHand,
  so_qty: so,
  spo_qty: spo,
});
const READ_ROWS = [row('BRW-IB', '10', '2'), row('MWH-IB', '5')];
const ZERO_ROW = row('DC1-BB', '0');
const INCOMING = [{ spo_number: 'SPO-77', spo_qty: '4', location: 'BRW-IB', expected_date: null }];
const STATUS = {
  product_id: 'prod-1',
  locations: [{ warehouse_id: 'wh-x', warehouse_code: 'OTHER-GROUP', warehouse_name: 'OTHER-GROUP' }],
  incoming_pl: [],
};

function answer(data: unknown) {
  useQuotationLineStockMock.mockReturnValue({ data, isLoading: false, isError: false });
}

beforeEach(() => {
  vi.clearAllMocks();
  answer({ locations: [...READ_ROWS, ZERO_ROW], incoming: INCOMING, available_qty: '-1988' });
  useStockDetailMock.mockReturnValue({ data: undefined, isLoading: false, isError: false });
  useStockStatusMock.mockReturnValue({ data: STATUS, isLoading: false });
});

function openPopover() {
  render(<QuotationStockChip productId="prod-1" quantity="2" uom="UNIT" label="SRTWB1515" />);
  fireEvent.click(screen.getByRole('button', { name: 'Stock on SRTWB1515' }));
}

describe('QuotationStockChip, QUOTE-STOCK-AGENT-LOC', () => {
  it('AC-QSA-21: reads the line product through useQuotationLineStock and shows N avail', () => {
    answer({ locations: READ_ROWS, incoming: [], available_qty: '25.00' });
    render(<QuotationStockChip productId="prod-1" quantity="10" uom="UNIT" label="SRTWB1515" />);
    expect(useQuotationLineStockMock).toHaveBeenCalledWith('prod-1');
    expect(useStockDetailMock).not.toHaveBeenCalled();
    const chip = screen.getByRole('button', { name: 'Stock on SRTWB1515' });
    expect(chip).toHaveTextContent('25 avail');
    expect(chip).toHaveAttribute('data-tone', 'ok');
  });

  it.each([
    ['4', 'part'],
    ['0', 'none'],
    ['-3', 'none'],
  ])('AC-QSA-21: %s available against 10 wanted is %s', (available, tone) => {
    answer({ locations: READ_ROWS, incoming: [], available_qty: available });
    render(<QuotationStockChip productId="prod-1" quantity="10" uom="UNIT" label="SRTWB1515" />);
    expect(screen.getByRole('button', { name: 'Stock on SRTWB1515' })).toHaveAttribute('data-tone', tone);
  });

  it('AC-QSA-22: a read answering null draws no chip and no text', () => {
    answer(null);
    const { container } = render(
      <QuotationStockChip productId="prod-1" quantity="2" uom="UNIT" label="SRTWB1515" />,
    );
    expect(useQuotationLineStockMock).toHaveBeenCalledWith('prod-1');
    expect(screen.queryByRole('button', { name: 'Stock on SRTWB1515' })).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it('AC-QSA-23: the table gets only the read locations, no all-zero row, no AutoCount extra', () => {
    openPopover();
    expect(screen.getAllByTestId('cell-stock-table')).toHaveLength(1);
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.locations).toEqual(READ_ROWS);
    expect(JSON.stringify(props.locations)).not.toContain('OTHER-GROUP');
    expect(JSON.stringify(props.locations)).not.toContain('DC1-BB');
  });

  it('AC-QSA-23: no group or pools stock read is made', () => {
    openPopover();
    expect(useStockDetailMock).not.toHaveBeenCalled();
  });

  it('AC-QSA-23: incoming lists the read incoming only', () => {
    openPopover();
    expect(screen.getByText('SPO-77')).toBeInTheDocument();
    expect(screen.getAllByText(/Incoming:/)).toHaveLength(1);
  });

  it('AC-QSA-23: a read with no incoming says so', () => {
    answer({ locations: READ_ROWS, incoming: [], available_qty: '3' });
    openPopover();
    expect(screen.getByText('No incoming SPO')).toBeInTheDocument();
  });
});

describe('STOCK-GROUPBY (AC-17, AC-20): the quotation popover carries the bar on the AutoCount mount only', () => {
  async function drawActual() {
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    const actual = await vi.importActual<
      typeof import('../../fulfilment-planning/components/CellStockTable')
    >('../../fulfilment-planning/components/CellStockTable');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <actual.CellStockTable {...(props as unknown as React.ComponentProps<typeof actual.CellStockTable>)} />
      </QueryClientProvider>,
    );
  }

  it('AC-20 with the read, the table shows the group-by-bar', async () => {
    useStockStatusMock.mockReturnValue({
      data: {
  product_id: 'prod-1',
  item_code: 'ITEM-1',
  locations: [{ warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', warehouse_name: 'BRW-BB', is_active: true, on_hand: 5, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 5 }],
  totals: { on_hand: 5, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 5, incoming_pl: 0, forecast_incl_pl: 5 },
  incoming_pl: [],
  sales_orders: [],
  purchase_orders: [],
  spos: [],
},
      isLoading: false,
    });
    openPopover();
    await drawActual();
    expect(screen.getByTestId('group-by-bar')).toBeInTheDocument();
  });

  it('AC-QSA-23: an AutoCount location the read did not list is not drawn in the popover table', async () => {
    useStockStatusMock.mockReturnValue({
      data: {
        product_id: 'prod-1',
        item_code: 'ITEM-1',
        locations: [
          { warehouse_id: 'wh-BRW-IB', warehouse_code: 'BRW-IB', warehouse_name: 'BRW-IB', is_active: true, on_hand: 10, so_qty: 2, po_qty: 0, spo_qty: 0, forecast: 8 },
          { warehouse_id: 'wh-WH3-BB', warehouse_code: 'WH3-BB', warehouse_name: 'WH3-BB', is_active: true, on_hand: 9, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 9 },
        ],
        totals: { on_hand: 19, so_qty: 2, po_qty: 0, spo_qty: 0, forecast: 17, incoming_pl: 0, forecast_incl_pl: 17 },
        incoming_pl: [],
        sales_orders: [],
        purchase_orders: [],
        spos: [],
      },
      isLoading: false,
    });
    openPopover();
    await drawActual();
    expect(screen.getAllByText(/BRW-IB/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/WH3-BB/)).not.toBeInTheDocument();
  });

  it('AC-17 without the read (a failed read), the table has no bar', async () => {
    useStockStatusMock.mockReturnValue({ data: undefined, isLoading: false });
    openPopover();
    await drawActual();
    expect(screen.queryByTestId('group-by-bar')).not.toBeInTheDocument();
  });
});
