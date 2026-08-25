/**
 * The stock position behind a cell, as a TABLE (captain, 18 August 2026).
 *
 * > "the representation of the BRW-BB on hand quantity, so quantity, PO quantity etc can be more
 * > tabulated and structured like AutoCount, with expandable details instead of clicking in"
 *
 * The strip it replaces printed one location as a run-on sentence
 * ("BRW-BB · 316 owed · On hand 478 · SO qty 47009 · SPO qty 0 · Available -46531"), which two
 * locations turned into two sentences nobody could compare column by column. So: a row per
 * location, AutoCount's own words as the headers, and the documents behind a location expanding
 * UNDER it rather than opening a second dialog.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getStockDetail = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
}));

import { CellStockTable } from './CellStockTable';
import type { BoardCellLocation } from '../../_shared/types/fulfilmentPlanning.types';

/** The captain's own location, as the live board sends it. */
function position(overrides: Partial<BoardCellLocation> = {}): BoardCellLocation {
  return {
    location: 'BRW-BB',
    product_id: 'prod-1',
    warehouse_id: 'wh-1',
    qty: '316',
    qty_demand: '316',
    qty_on_hand: '478',
    qty_reserved: '0',
    qty_free: '478',
    so_qty: '47009',
    spo_qty: '0',
    available_qty: '-46531',
    incoming: [],
    ...overrides,
  };
}

function renderTable(locations: BoardCellLocation[], groupNote?: string | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <CellStockTable
        locations={locations}
        itemCode="B2155-NL-BLUE"
        groupNote={groupNote}
      />
    </QueryClientProvider>,
  );
}

function headers(): string[] {
  return [...screen.getByRole('table').querySelectorAll('thead th')].map(
    (cell) => cell.textContent ?? '',
  );
}

function cellsOf(location: string): string[] {
  return [...screen.getByTestId(`cell-location-${location}`).querySelectorAll('td, th')].map(
    (cell) => cell.textContent ?? '',
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CellStockTable: the position, tabulated', () => {
  it('carries AutoCount’s own words as its headers, in AutoCount’s order', () => {
    renderTable([position()]);

    // No demand column. It read "Owed here" and it said what the Contributing lines table
    // below already says line by line under Outstanding. No Free column either: it is
    // `On hand - Reserved`, both of which are here, so it restated what the reader can see.
    expect(headers()).toEqual([
      '',
      'Location',
      'Where',
      'On hand',
      'Reserved',
      'SO qty',
      'SPO qty',
      'Available',
    ]);
  });

  it('renders one row per location, with the figures the server sent', () => {
    renderTable([
      position(),
      position({
        location: 'BRW',
        warehouse_id: 'wh-2',
        qty: '9',
        qty_demand: '9',
        qty_on_hand: '1015',
        qty_reserved: '12',
        qty_free: '1003',
        so_qty: '9028',
        spo_qty: '500',
        available_qty: '-7513',
      }),
    ]);

    expect(screen.getByRole('table').querySelectorAll('tbody tr')).toHaveLength(2);
    expect(cellsOf('BRW-BB')).toEqual([
      '',
      'BRW-BB',
      'Own location',
      '478',
      '0',
      '47009',
      '0',
      '-46531',
    ]);
    expect(cellsOf('BRW')).toEqual([
      '',
      'BRW',
      'Own location',
      '1015',
      '12',
      '9028',
      '500',
      '-7513',
    ]);
  });

  it('reads the numbers as numbers: right-aligned tabular figures', () => {
    renderTable([position()]);

    const available = screen.getByTestId('stock-available-BRW-BB');
    expect(available.className).toContain('tabular-nums');
    expect(available.className).toContain('text-end');
  });

  /**
   * A negative Available IS the shortfall. It is never clamped, and it is coloured, because it
   * is the one number on the row that says "this cannot be met from here".
   */
  it('colours a negative Available, and leaves a positive one alone', () => {
    renderTable([
      position(),
      position({ location: 'BRW', warehouse_id: 'wh-2', available_qty: '120' }),
    ]);

    expect(screen.getByTestId('stock-available-BRW-BB').className).toContain('text-destructive');
    expect(screen.getByTestId('stock-available-BRW').className).not.toContain('text-destructive');
  });

  /**
   * The opposite instruction: 0 free means do not look here, nothing stated means nobody has
   * said where to look. A line whose sales order names no location has every figure null by
   * construction.
   */
  it('says NOT STATED, never 0, when the sales order named no location', () => {
    renderTable([
      {
        location: null,
        qty: '24',
        qty_on_hand: null,
        qty_reserved: null,
        qty_free: null,
        so_qty: null,
        spo_qty: null,
        available_qty: null,
      },
    ]);

    const cells = cellsOf('none');
    expect(cells[1]).toBe('No location');
    expect(cells.slice(3)).toEqual([
      'Not stated',
      'Not stated',
      'Not stated',
      'Not stated',
      'Not stated',
    ]);
    expect(cells).not.toContain('0');
  });

  /** Measured live: a location can carry `so_qty` while `qty_on_hand` is null. */
  it('shows whichever figure the server stated, not all-or-nothing', () => {
    renderTable([
      position({
        location: 'BRW-IB',
        qty_on_hand: null,
        qty_reserved: null,
        qty_free: null,
        so_qty: '10805',
        spo_qty: '0',
        available_qty: null,
      }),
    ]);

    const cells = cellsOf('BRW-IB');
    expect(cells[3]).toBe('Not stated');
    expect(cells[5]).toBe('10805');
    expect(cells[6]).toBe('0');
    expect(cells[7]).toBe('Not stated');
  });

  it('scrolls inside its own container, so the dialog never scrolls sideways', () => {
    renderTable([position()]);

    expect(screen.getByTestId('cell-stock-table').className).toContain('overflow-x-auto');
    // `w-full`, so the table reaches the edge of the dialog instead of stopping two thirds
    // across and leaving a blank band beside it - and never `table-fixed`, which overlaps its
    // columns as soon as the content is wider than the declared width. A narrow dialog still
    // overflows past the per-column floors and the container above scrolls it.
    const table = screen.getByRole('table');
    expect(table.className).toContain('w-full');
    expect(table.className).not.toContain('w-max');
    expect(table.className).not.toContain('table-fixed');
  });

  it('states an empty position rather than rendering an empty table', () => {
    renderTable([]);

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('No stock position for this cell')).toBeInTheDocument();
  });
});

describe('CellStockTable: where each location stands', () => {
  /**
   * The captain, on SO415472: the card read "Use own location 71 from BRW - Pool BRW has 1716
   * available" over a table of five -BB warehouses, every one of them "Not stated". The pool is
   * a warehouse of its own and it was not in the agent's group, so nothing listed it and the
   * one figure the decision rested on could not be checked against anything.
   *
   * The server now sends every location the ladder consulted, each tagged with where it stands,
   * and the tag is a column: a site pool holding 1716 and a group warehouse holding nothing are
   * not the same kind of row, and unlabelled they look identical.
   */
  it('names where each location stands, so a site pool is not read as a group warehouse', () => {
    renderTable([
      position({ where: 'own' }),
      position({ location: 'DC1-BB', warehouse_id: 'wh-2', where: 'group' }),
      position({
        location: 'BRW',
        warehouse_id: 'wh-3',
        where: 'site_pool',
        qty_on_hand: '1728',
        so_qty: '12',
        spo_qty: '0',
        available_qty: '1716',
      }),
      position({ location: 'BRW-IR', warehouse_id: 'wh-4', where: 'other_group' }),
    ]);

    expect(cellsOf('BRW-BB')[2]).toBe('Own location');
    expect(cellsOf('DC1-BB')[2]).toBe('Group');
    expect(cellsOf('BRW')[2]).toBe('Site pool');
    expect(cellsOf('BRW-IR')[2]).toBe('Other group');
    // And the figure the Suggestion card quotes is a row of the table, not a number only the
    // sentence knows.
    expect(screen.getByTestId('stock-available-BRW').textContent).toBe('1716');
  });

  it('subtotals a section of several rows once the table spans more than one', () => {
    renderTable([
      position({ where: 'group', qty_on_hand: '10', available_qty: '10' }),
      position({
        location: 'DC1-BB',
        warehouse_id: 'wh-2',
        where: 'group',
        qty_on_hand: '5',
        available_qty: '5',
      }),
      position({
        location: 'BRW',
        warehouse_id: 'wh-3',
        where: 'site_pool',
        qty_on_hand: '1728',
        available_qty: '1716',
      }),
    ]);

    const subtotal = [
      ...screen.getByTestId('stock-subtotal-group').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    expect(subtotal).toContain('Group subtotal');
    expect(subtotal).toContain('15');
    // One row IS its own subtotal, so the pool section does not repeat itself.
    expect(screen.queryByTestId('stock-subtotal-site_pool')).not.toBeInTheDocument();
    // The Total is still the whole table.
    const footer = [...screen.getByRole('table').querySelectorAll('tfoot td')].map(
      (entry) => entry.textContent ?? '',
    );
    expect(footer).toContain('Total');
    expect(footer).toContain('1743');
  });

  it('adds no subtotal when every location stands in the same place', () => {
    // The subtotal would then be the Total, printed twice under two different words.
    renderTable([
      position(),
      position({ location: 'DC1-BB', warehouse_id: 'wh-2' }),
    ]);

    expect(screen.queryByTestId('stock-subtotal-own')).not.toBeInTheDocument();
  });
});

describe('CellStockTable: the totals row', () => {
  it('totals the quantities once there is more than one location to add up', () => {
    renderTable([
      position(),
      position({
        location: 'BRW',
        warehouse_id: 'wh-2',
        qty: '9',
        qty_on_hand: '1015',
        qty_reserved: '12',
        qty_free: '1003',
        so_qty: '9028',
        spo_qty: '500',
        available_qty: '-7513',
      }),
    ]);

    const footer = [...(screen.getByRole('table').querySelectorAll('tfoot td, tfoot th') ?? [])].map(
      (cell) => cell.textContent ?? '',
    );
    // EVERY column totals now, Reserved included: the rows are a whole ownership group rather
    // than one warehouse, and "what does the group hold" is why it is listed.
    expect(footer).toContain('Total');
    expect(footer).toContain('1493');
    expect(footer).toContain('12');
    expect(footer).toContain('56037');
    expect(footer).toContain('500');
    expect(footer).toContain('-54044');
    // The demand is not in it, because there is no demand column any more.
    expect(footer).not.toContain('325');
  });

  /** One row IS its own total, and a totals row that repeats it is a row saying nothing. */
  it('has no totals row for a single location', () => {
    renderTable([position()]);

    expect(screen.getByRole('table').querySelector('tfoot')).toBeNull();
  });
});

describe('CellStockTable: the documents, expanded in place', () => {
  const detail = {
    product_id: 'prod-1',
    item_code: 'B2155-NL-BLUE',
    warehouse_id: 'wh-1',
    location: 'BRW-BB',
    qty_on_hand: '478',
    so_qty: '47009',
    spo_qty: '0',
    available_qty: '-46531',
    qty_reserved: '0',
    qty_held_by_decisions: '0',
    qty_free: '478',
    sales_orders: [
      {
        sales_order_id: 'so-a',
        so_number: 'SO391698',
        customer_name: 'OIB CONSTRUCTION SDN BHD',
        doc_date: '2026-01-05',
        delivery_date: '2026-09-04',
        so_qty: '47009',
        is_covered: false,
      },
    ],
    incoming: [],
  };

  it('opens the documents under the row, addressed by the ids the server sent', async () => {
    getStockDetail.mockResolvedValue(detail);
    renderTable([position()]);

    expect(screen.queryByTestId('stock-documents-panel')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Show documents behind BRW-BB' }),
    );

    await waitFor(() => expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-1'));
    const expansion = await screen.findByTestId('stock-expansion-BRW-BB');
    expect(within(expansion).getByTestId('stock-documents-panel')).toBeInTheDocument();
    expect(await within(expansion).findByText('SO391698')).toBeInTheDocument();
  });

  it('closes again on a second press, without navigating anywhere', async () => {
    getStockDetail.mockResolvedValue(detail);
    renderTable([position()]);

    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    await screen.findByTestId('stock-expansion-BRW-BB');

    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    expect(screen.queryByTestId('stock-expansion-BRW-BB')).not.toBeInTheDocument();
  });

  it('lets two locations stand open at once, because comparing them is the point', async () => {
    getStockDetail.mockResolvedValue(detail);
    renderTable([
      position(),
      position({ location: 'BRW', warehouse_id: 'wh-2' }),
    ]);

    fireEvent.click(screen.getByTestId('stock-expand-BRW-BB'));
    fireEvent.click(screen.getByTestId('stock-expand-BRW'));

    await screen.findByTestId('stock-expansion-BRW-BB');
    expect(screen.getByTestId('stock-expansion-BRW')).toBeInTheDocument();
    await waitFor(() => expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-2'));
  });

  /**
   * Two products on the live book share the code B2155-NL-BLUE, so a position the server did
   * not address by ids cannot be drilled into at all - resolving one from the code would answer
   * confidently about the wrong product.
   */
  it('offers no chevron for a position the server cannot address, and says why', () => {
    renderTable([position({ product_id: null, warehouse_id: null })]);

    expect(screen.queryByTestId('stock-expand-BRW-BB')).not.toBeInTheDocument();
    expect(screen.getByTitle('Not addressable')).toBeInTheDocument();
  });
});

/**
 * The rows are normally the sales agent's whole ownership group - BRW-BB, MWH-BB and DC1-BB
 * are one group belonging to the BB salespeople - because "can I fulfil this" is a question
 * about the group, not about the one warehouse the line happens to name.
 *
 * When no group could be resolved the table says so. A single row with nothing said about it
 * reads as "this product lives in exactly one place", which is the belief the group listing
 * exists to correct.
 */
describe('CellStockTable: the ownership group', () => {
  it('tabulates every location the server sent, group members included', () => {
    renderTable([
      position(),
      position({ location: 'MWH-BB', warehouse_id: 'wh-2', qty: '0', qty_demand: '0', qty_on_hand: '25' }),
      position({ location: 'DC1-BB', warehouse_id: 'wh-3', qty: '0', qty_demand: '0', qty_on_hand: '0' }),
    ]);

    expect(screen.getByRole('table').querySelectorAll('tbody tr')).toHaveLength(3);
    expect(cellsOf('MWH-BB')[3]).toBe('25');
    // Listed even holding nothing: "nothing at DC1-BB" is an answer, a missing row is not.
    expect(cellsOf('DC1-BB')[3]).toBe('0');
  });

  it('says why, when the line\u2019s own location is all there is', () => {
    renderTable([position()], 'Agent SEAN has no location group.');

    expect(screen.getByTestId('cell-stock-group-note').textContent).toBe(
      'Agent SEAN has no location group.',
    );
  });

  it('says nothing extra when a group WAS resolved', () => {
    renderTable([position()], null);

    expect(screen.queryByTestId('cell-stock-group-note')).not.toBeInTheDocument();
  });

  it('still says why when there is no position to tabulate at all', () => {
    renderTable([], 'No sales agent on the order, so no location group.');

    expect(screen.getByText('No stock position for this cell')).toBeInTheDocument();
    expect(screen.getByTestId('cell-stock-group-note').textContent).toBe(
      'No sales agent on the order, so no location group.',
    );
  });
});
