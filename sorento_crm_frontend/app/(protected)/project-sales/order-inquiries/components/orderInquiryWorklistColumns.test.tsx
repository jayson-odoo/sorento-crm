/**
 * The list's own "Outstanding PO/SPO" column (AC-D2/AC-D3/AC-D16/AC-D17, item 5 and 11 of
 * `PLAN-scm-oi-draft-links.md`): the SAME `SupplyBar` the schedule matrix draws, off the
 * same three kinds, under the coverage headline, plus the draft/confirmed mark and the
 * per-document location-first summary. Rendered here as a bare `<table>` off
 * `useOrderInquiryWorklistColumns()` directly - just the one column, so a DataGrid's own
 * chrome (which needs `useListingColumnPreferences` mocked under jsdom, see
 * `OrderInquiriesClient.test.tsx`) never has to enter this test at all.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

function worklistRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    verb: 'ORDER',
    links: [],
    linked_qty: '0',
    ...over,
  } as OrderInquiryWorklistRow;
}

/** Just the "Outstanding PO/SPO" column - the bar and the draft mark live entirely in
 * this one cell, and nothing else on this row is under test here. */
function LinkedToOnly({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const allColumns = useOrderInquiryWorklistColumns();
  const linkedColumn = allColumns.find(
    (column) => (column as ColumnDef<OrderInquiryWorklistRow> & { id?: string }).id === 'po_number',
  )!;
  const table = useReactTable({
    data: rows,
    columns: [linkedColumn],
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid={`row-${row.original.id}`}>
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderRows(rows: OrderInquiryWorklistRow[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LinkedToOnly rows={rows} />
    </QueryClientProvider>,
  );
}

describe('the "Outstanding PO/SPO" column: the bar (AC-I14)', () => {
  it('draws the bar on a row wholly linked to a purchase order', () => {
    renderRows([
      worklistRow({
        id: 'row-linked',
        qty: '35',
        linked_qty: '35',
        po_number: '202601-S0015',
        links: [{ id: 'l1', kind: 'po', document: '202601-S0015', qty: '35', po_id: 'po-1' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-linked');
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'true');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('po');
  });

  it('draws a split sky/rose bar for a row linked 5 of 8 to a purchase order', () => {
    renderRows([
      worklistRow({
        id: 'row-split',
        qty: '8',
        linked_qty: '5',
        po_number: '202601-S0044',
        links: [
          { id: 'l1', kind: 'po', document: '202601-S0044', qty: '5', po_id: 'po-2' },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-split');
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const kinds = [...bar.querySelectorAll('span[data-kind]')].map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(kinds).toEqual(['po', 'buy']);
  });

  it('draws no bar at all for a cancelled row - it owes nothing', () => {
    renderRows([
      worklistRow({ id: 'row-cancelled', qty: '6', linked_qty: '0', links: [], state: 'cancelled' }),
    ]);

    const row = screen.getByTestId('row-row-cancelled');
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });
});

describe('AC-D2: a row nothing can cover', () => {
  it('reads "Not found (new order)" - never "Not linked", which read as an oversight', () => {
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(within(row).getByText('Not found (new order)')).toBeInTheDocument();
    expect(within(row).queryByText('Not linked')).not.toBeInTheDocument();
    // The bar still draws - a solid rose Buy segment - so the row is not a blank cell.
    const bar = within(row).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('buy');
  });

  it('carries no draft/confirmed mark at all when there is nothing to mark', () => {
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(within(row).queryByTestId('link-draft-mark')).not.toBeInTheDocument();
    expect(within(row).queryByTestId('link-confirmed-mark')).not.toBeInTheDocument();
  });
});

describe('AC-D1/D3: the draft vs confirmed mark reads off ack_state, not a link column', () => {
  function linkedRow(over: Partial<OrderInquiryWorklistRow> = {}) {
    return worklistRow({
      id: 'row-linked',
      qty: '10',
      linked_qty: '10',
      po_number: '202607-S0105',
      links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '10', po_id: 'po-1' }],
      ...over,
    });
  }

  it('marks a link on an awaiting row DRAFT (the default ack_state)', () => {
    renderRows([linkedRow()]);
    const row = screen.getByTestId('row-row-linked');
    expect(within(row).getByTestId('link-draft-mark')).toBeInTheDocument();
    expect(within(row).queryByTestId('link-confirmed-mark')).not.toBeInTheDocument();
  });

  it('marks a link on a CHANGED row draft too - purchasing has to look again', () => {
    renderRows([linkedRow({ ack_state: 'changed' })]);
    const row = screen.getByTestId('row-row-linked');
    expect(within(row).getByTestId('link-draft-mark')).toBeInTheDocument();
  });

  it('marks a link on an ACKNOWLEDGED row confirmed, with who and when in the title', () => {
    renderRows([
      linkedRow({
        ack_state: 'acknowledged',
        acknowledged_by_name: 'Joey Ang',
        acknowledged_at: '2026-08-27T01:56:00',
      }),
    ]);
    const row = screen.getByTestId('row-row-linked');
    const mark = within(row).getByTestId('link-confirmed-mark');
    expect(mark).toBeInTheDocument();
    expect(within(row).queryByTestId('link-draft-mark')).not.toBeInTheDocument();
    expect(mark.getAttribute('title')).toContain('Joey Ang');
  });

  it('renders no mark at all for a rejected row - its links are gone, nothing to mark', () => {
    renderRows([linkedRow({ ack_state: 'rejected' })]);
    const row = screen.getByTestId('row-row-linked');
    expect(within(row).queryByTestId('link-draft-mark')).not.toBeInTheDocument();
    expect(within(row).queryByTestId('link-confirmed-mark')).not.toBeInTheDocument();
  });
});

describe('AC-D16/AC-D17: the per-document summary reads location first, late N d', () => {
  it('reads the pool warehouse code and quantity, the line label only in the title', () => {
    renderRows([
      worklistRow({
        id: 'row-spo',
        qty: '1',
        linked_qty: '1',
        po_number: 'SPO-2026/08-0015',
        links: [
          {
            id: 'l1',
            kind: 'spo',
            document: 'SPO-2026/08-0015',
            line_label: 'L14',
            location: 'BRW',
            qty: '1',
          },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-spo');
    // The visible text is "BRW 1" - never "L14 1".
    expect(within(row).getByText('BRW 1')).toBeInTheDocument();
    expect(within(row).queryByText('L14 1')).not.toBeInTheDocument();
    // The document's title carries the label AND the location.
    expect(within(row).getByTitle(/L14 BRW 1/)).toBeInTheDocument();
  });

  it('reads "no location" when the book named none', () => {
    renderRows([
      worklistRow({
        id: 'row-noloc',
        qty: '5',
        linked_qty: '5',
        po_number: '202607-S0105',
        links: [
          { id: 'l1', kind: 'po', document: '202607-S0105', qty: '5', location: null },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-noloc');
    expect(within(row).getByText('no location 5')).toBeInTheDocument();
  });

  it('reads "late N d" with the full dates in the title', () => {
    renderRows([
      worklistRow({
        id: 'row-late',
        qty: '5',
        linked_qty: '5',
        delivery_date: '2026-08-01',
        po_number: '202607-S0105',
        links: [
          {
            id: 'l1',
            kind: 'po',
            document: '202607-S0105',
            qty: '5',
            location: 'BRW',
            late: true,
            late_days: 12,
          },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-late');
    const badge = within(row).getByTestId('link-late-202607-S0105');
    expect(badge).toHaveTextContent('late 12 d');
  });
});
