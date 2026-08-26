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

function renderTable(
  locations: BoardCellLocation[],
  groupNote?: string | null,
  taken?: Map<string, string>,
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <CellStockTable
        locations={locations}
        itemCode="B2155-NL-BLUE"
        groupNote={groupNote}
        taken={taken}
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
    // below already says line by line under Outstanding. No Reserved and no Free: Free was
    // `On hand - Reserved`, and Reserved was read by nothing here once Available turned out
    // not to use it. PO qty and Taken took the room, and each answers a question no other
    // number on the row does.
    expect(headers()).toEqual([
      '',
      'Location',
      'Where',
      'On hand',
      'SO qty',
      'SPO qty',
      'Available',
      'PO qty',
      'Taken',
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
      '47009',
      '0',
      '-46531',
      '0',
      '0',
    ]);
    expect(cellsOf('BRW')).toEqual([
      '',
      'BRW',
      'Own location',
      '1015',
      '9028',
      '500',
      '-7513',
      '0',
      '0',
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
   * The one row that can still be blank, and the reason it is: there is no location whose
   * stock could be counted, so a 0 would read as "that location is empty". Every OTHER row
   * names a location, and AC-B2 makes it read 0.
   */
  it('leaves the figures blank when the sales order named no location', () => {
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
    expect(cells.slice(3)).toEqual(['-', '-', '-', '-', '-', '-']);
    expect(cells).not.toContain('0');
    // The phrase is gone from the table: it was the answer to a question this table no
    // longer asks (AC-B2).
    expect(screen.queryByText('Not stated')).not.toBeInTheDocument();
  });

  /**
   * AC-B2. An absent `stock` row is not an unknown: the last upload counted none there, and
   * "0" is what lets the reader rule the location out instead of wondering about it.
   */
  it('reads 0, never "Not stated", for a location with no stock upload', () => {
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
    expect(cells[3]).toBe('0');
    // The figures the server DID state are untouched by the rule.
    expect(cells[4]).toBe('10805');
    expect(cells[5]).toBe('0');
    expect(cells[6]).toBe('0');
    expect(screen.queryByText('Not stated')).not.toBeInTheDocument();
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
    // EVERY column totals: the rows are a whole ownership group rather than one warehouse,
    // and "what does the group hold" is why it is listed.
    expect(footer).toContain('Total');
    expect(footer).toContain('1493');
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

/**
 * AC-B1. The captain, on SO415472: "why is BRW the only pool considered? What about MWH, DC1,
 * WH3?" They were, and the table now says so - the server sends every pool it walked, and each
 * section of the table adds itself up so a pool's figure is a row rather than a sentence.
 */
describe('CellStockTable: the whole ladder, in sections', () => {
  /** The live shape of a BRW-BB line: own, four group siblings, five pools. */
  function ladder(): BoardCellLocation[] {
    return [
      position({ where: 'own', qty_on_hand: '40', available_qty: '40' }),
      ...['MWH-BB', 'DC1-BB', 'WH3-BB', 'RSW-BB'].map((location, index) =>
        position({
          location,
          warehouse_id: `wh-g${index}`,
          where: 'group',
          qty_on_hand: '10',
          so_qty: '0',
          spo_qty: '0',
          available_qty: '10',
        }),
      ),
      ...['BRW', 'MWH', 'DC1', 'WH3', 'RSW'].map((location, index) =>
        position({
          location,
          warehouse_id: `wh-p${index}`,
          where: 'site_pool',
          qty_on_hand: '100',
          so_qty: '0',
          spo_qty: '0',
          available_qty: '100',
        }),
      ),
    ];
  }

  function rowOrder(): string[] {
    return [...screen.getByRole('table').querySelectorAll('tbody tr')]
      .map((row) => row.querySelectorAll('td')[1]?.textContent ?? '')
      .filter((label) => !label.endsWith('subtotal'));
  }

  it('lists the own location, then the group, then every pool, each tagged', () => {
    renderTable(ladder());

    expect(rowOrder()).toEqual([
      'BRW-BB',
      'MWH-BB',
      'DC1-BB',
      'WH3-BB',
      'RSW-BB',
      'BRW',
      'MWH',
      'DC1',
      'WH3',
      'RSW',
    ]);
    expect(cellsOf('BRW-BB')[2]).toBe('Own location');
    expect(cellsOf('RSW-BB')[2]).toBe('Group');
    expect(cellsOf('RSW')[2]).toBe('Site pool');
  });

  it('subtotals each section and totals the table', () => {
    renderTable(ladder());

    const group = [
      ...screen.getByTestId('stock-subtotal-group').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    expect(group).toContain('Group subtotal');
    expect(group).toContain('40');

    const pool = [
      ...screen.getByTestId('stock-subtotal-site_pool').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    expect(pool).toContain('Site pool subtotal');
    expect(pool).toContain('500');

    const footer = [...screen.getByRole('table').querySelectorAll('tfoot td')].map(
      (entry) => entry.textContent ?? '',
    );
    expect(footer).toContain('Total');
    expect(footer).toContain('580');
  });

  /**
   * A pool the ladder took nothing from is the point of listing it: the row itself answers
   * "why not MWH" - it was there, it held 100, and nothing was needed from it.
   */
  it('shows what a pool holds even when nothing was drawn from it', () => {
    renderTable(ladder(), null, new Map([['BRW', '71']]));

    expect(cellsOf('BRW')[7]).toBe('0');
    expect(cellsOf('BRW')[8]).toBe('71');
    expect(cellsOf('MWH')[8]).toBe('0');
  });
});

describe('CellStockTable: PO qty and Taken', () => {
  it('shows the open PO balance the server states, and 0 where it states none', () => {
    renderTable([
      position({ po_open_qty: '380' }),
      position({ location: 'DC1-BB', warehouse_id: 'wh-2', where: 'group' }),
    ]);

    expect(screen.getByTestId('stock-po-BRW-BB').textContent).toBe('380');
    expect(screen.getByTestId('stock-po-DC1-BB').textContent).toBe('0');
  });

  /**
   * AC-B3. The Taken column sums to the quantity needed when the line is covered from stock,
   * and every row nothing was drawn from reads 0.
   */
  it('adds the Taken column up to the quantity the cell drew', () => {
    renderTable(
      [
        position({ location: 'DC1-BB', warehouse_id: 'wh-1', where: 'group' }),
        position({ location: 'MWH-BB', warehouse_id: 'wh-2', where: 'group' }),
        position({ location: 'WH3-BB', warehouse_id: 'wh-3', where: 'group' }),
        position({ location: 'BRW', warehouse_id: 'wh-4', where: 'site_pool' }),
      ],
      null,
      new Map([
        ['DC1-BB', '454'],
        ['MWH-BB', '267'],
        ['WH3-BB', '211'],
      ]),
    );

    expect(screen.getByTestId('stock-taken-DC1-BB').textContent).toBe('454');
    expect(screen.getByTestId('stock-taken-MWH-BB').textContent).toBe('267');
    expect(screen.getByTestId('stock-taken-WH3-BB').textContent).toBe('211');
    // Listed, and drawn on for nothing.
    expect(screen.getByTestId('stock-taken-BRW').textContent).toBe('0');

    const footer = [...screen.getByRole('table').querySelectorAll('tfoot td')].map(
      (entry) => entry.textContent ?? '',
    );
    expect(footer).toContain('932');
  });

  it('reads 0 everywhere for a cell that draws on no stock at all', () => {
    // A Buy-only cell: nothing is held anywhere, so nothing is taken from anywhere.
    renderTable([position(), position({ location: 'BRW', warehouse_id: 'wh-2' })]);

    expect(screen.getByTestId('stock-taken-BRW-BB').textContent).toBe('0');
    expect(screen.getByTestId('stock-taken-BRW').textContent).toBe('0');
  });
});

/**
 * AC-L12 (ladder v4, ruled 26 August 2026): the subtotal prints the NET the engine obeyed.
 *
 * `B2155-NL-BLUE` is the case the ruling came from. `MWH-IB` reads 7000 available and lends
 * nothing, because the IB group it belongs to nets -15514 - and a table that showed only the
 * per-row figure could not explain why nothing was taken from it. The net is over the WHOLE
 * group, silent members included, so it is stated by the server rather than summed here.
 */
describe('CellStockTable: the net the ladder obeyed (AC-L12)', () => {
  const ibGroup = () => [
    position({
      location: 'BRW-IB',
      warehouse_id: 'wh-brw-ib',
      where: 'own',
      qty_on_hand: '5290',
      so_qty: '27804',
      spo_qty: '0',
      available_qty: '-22514',
      net: '-15514',
      net_of: 'IB',
    }),
    position({
      location: 'MWH-IB',
      warehouse_id: 'wh-mwh-ib',
      where: 'group',
      qty_on_hand: '7000',
      so_qty: '0',
      spo_qty: '0',
      available_qty: '7000',
      net: '-15514',
      net_of: 'IB',
    }),
    position({
      location: 'BRW',
      warehouse_id: 'wh-brw',
      where: 'site_pool',
      qty_on_hand: '0',
      so_qty: '103',
      spo_qty: '0',
      available_qty: '-103',
      net: '-102',
      net_of: 'pools',
    }),
    position({
      location: 'DC1',
      warehouse_id: 'wh-dc1',
      where: 'site_pool',
      qty_on_hand: '1',
      so_qty: '0',
      spo_qty: '0',
      available_qty: '1',
      net: '-102',
      net_of: 'pools',
    }),
  ];

  it('subtotals the own location WITH its group, and prints the group net', () => {
    renderTable(ibGroup());

    const subtotal = [
      ...screen.getByTestId('stock-subtotal-IB').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    // One ownership group, one subtotal, whatever Where tag each row carries: the tag says
    // where a row stands relative to this cell, the net says which pile it is part of.
    expect(subtotal).toContain('IB group subtotal');
    // Available takes the server's NET; every other column still adds up the rows on
    // screen, which is what makes the two readable side by side - 12290 sits at these two
    // locations, and -15514 is what the group has once its book is counted.
    expect(screen.getByTestId('stock-subtotal-available-IB').textContent).toBe('-15514');
    expect(subtotal).toContain('12290');
  });

  it('says on the subtotal why the Available figure is not the column added up', () => {
    // A tooltip, not a line of copy: the number is the point, and the one thing a reader
    // cannot see is that the net covers locations this table never listed.
    renderTable(ibGroup());

    expect(
      screen.getByTestId('stock-subtotal-available-IB').getAttribute('title'),
    ).toBe('-15514 across every IB location, including any this table does not list');
    expect(
      screen.getByTestId('stock-subtotal-available-pools').getAttribute('title'),
    ).toBe('-102 across every site pool, including any this table does not list');
    // Every other subtotal cell IS its column added up, so it explains nothing.
    expect(
      screen.getByTestId('stock-subtotal-on-hand-IB').getAttribute('title'),
    ).toBeNull();
  });

  it('lists a donor group whole, with its own net as the subtotal (AC-V3)', () => {
    // Ladder v5, section 1e. The ladder drew from DC1-NTC; the offer was the NTC GROUP's
    // net, so BRW-NTC comes with it even though no proposal named it. Each row keeps its
    // OWN signed available, and the subtotal is the group's net - which is what a reader
    // needs to check "why only 100" against.
    renderTable([
      position({ location: 'BRW-BB', where: 'own', net: '-969', net_of: 'BB' }),
      position({
        location: 'DC1-NTC',
        warehouse_id: 'wh-dc1-ntc',
        where: 'other_group',
        qty: '0',
        qty_demand: '0',
        qty_on_hand: '100',
        so_qty: '0',
        spo_qty: '0',
        available_qty: '100',
        net: '166',
        net_of: 'NTC',
      }),
      position({
        location: 'BRW-NTC',
        warehouse_id: 'wh-brw-ntc',
        where: 'other_group',
        qty: '0',
        qty_demand: '0',
        qty_on_hand: '80',
        so_qty: '14',
        spo_qty: '0',
        available_qty: '66',
        net: '166',
        net_of: 'NTC',
      }),
    ]);

    // Both sites of the donor group are on screen, each with its own signed available.
    expect(cellsOf('DC1-NTC')).toContain('100');
    expect(cellsOf('BRW-NTC')).toContain('66');
    // ONE subtotal for the group, carrying the group's net rather than the two rows added.
    const subtotal = [
      ...screen.getByTestId('stock-subtotal-NTC').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    expect(subtotal).toContain('NTC group subtotal');
    expect(screen.getByTestId('stock-subtotal-available-NTC').textContent).toBe('166');
  });

  it('prints the site pools net rather than the pools on screen', () => {
    renderTable(ibGroup());

    expect(screen.getByTestId('stock-subtotal-available-pools').textContent).toBe('-102');
    const subtotal = [
      ...screen.getByTestId('stock-subtotal-pools').querySelectorAll('td'),
    ].map((entry) => entry.textContent ?? '');
    expect(subtotal).toContain('Site pool subtotal');
  });

  it('prints a net for a section of ONE row, because the rows cannot say it', () => {
    // The net covers every location of the group; this table lists the ones the cell
    // consulted. A single row that IS its own sum still cannot state the group's position.
    renderTable([
      position({ where: 'own', available_qty: '10', net: '-40', net_of: 'BB' }),
      position({
        location: 'BRW',
        warehouse_id: 'wh-brw',
        where: 'site_pool',
        available_qty: '5',
        net: '5',
        net_of: 'pools',
      }),
    ]);

    expect(screen.getByTestId('stock-subtotal-available-BB').textContent).toBe('-40');
  });

  it('draws only from the set that has something, and reads 0 on the ones that do not', () => {
    // The engine cannot draw on a set that nets zero or less, so what it hands the table
    // draws from the IR group alone. The rows of the two sets it could not touch read 0 -
    // which is the answer to "why not MWH-IB", said by the row itself - and the drawn row
    // reads its own quantity, so the column is not simply blank everywhere.
    renderTable(
      [
        ...ibGroup(),
        position({
          location: 'MWH-IR',
          warehouse_id: 'wh-mwh-ir',
          where: 'other_group',
          qty_on_hand: '100',
          so_qty: '0',
          available_qty: '100',
          net: '100',
          net_of: 'IR',
        }),
      ],
      null,
      new Map([['MWH-IR', '60']]),
    );

    expect(screen.getByTestId('stock-taken-MWH-IR').textContent).toBe('60');
    expect(screen.getByTestId('stock-subtotal-taken-IR').textContent).toBe('60');
    expect(screen.getByTestId('stock-taken-BRW-IB').textContent).toBe('0');
    expect(screen.getByTestId('stock-taken-MWH-IB').textContent).toBe('0');
    expect(screen.getByTestId('stock-taken-DC1').textContent).toBe('0');
    expect(screen.getByTestId('stock-subtotal-taken-IB').textContent).toBe('0');
    expect(screen.getByTestId('stock-subtotal-taken-pools').textContent).toBe('0');
  });

  it('falls back to the sum where the server states no net', () => {
    // Nothing on the wire, nothing invented: a cell whose rows carry no net is the old
    // table, and its subtotal is what the rows add up to.
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

    expect(screen.getByTestId('stock-subtotal-available-group').textContent).toBe('15');
  });
});
