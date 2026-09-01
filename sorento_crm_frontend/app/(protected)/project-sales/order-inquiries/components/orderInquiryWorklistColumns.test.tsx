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

/** One named column at a time - the bar/draft-mark/rejected-note/Was-Now live entirely
 * in their own cell, and nothing else on the row is under test in any of these files. */
function OneColumnOnly({
  rows,
  columnId,
}: {
  rows: OrderInquiryWorklistRow[];
  columnId: string;
}) {
  const allColumns = useOrderInquiryWorklistColumns();
  const named = allColumns.find((column) => {
    const withKeys = column as ColumnDef<OrderInquiryWorklistRow> & {
      id?: string;
      accessorKey?: string;
    };
    // A column's `id` on the RAW def is only set when given explicitly (`po_number`);
    // one built off a bare `accessorKey` (`qty`) only gets an `id` once react-table
    // resolves the column internally, so the lookup has to try both.
    return withKeys.id === columnId || withKeys.accessorKey === columnId;
  })!;
  const table = useReactTable({
    data: rows,
    columns: [named],
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

function renderRows(rows: OrderInquiryWorklistRow[], columnId = 'po_number') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OneColumnOnly rows={rows} columnId={columnId} />
    </QueryClientProvider>,
  );
}

function renderQtyCell(rows: OrderInquiryWorklistRow[]) {
  return renderRows(rows, 'qty');
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

describe('the qty cell: rejected reason and Was/Now (S1 AC-1.5, S7 review of PR #471)', () => {
  it('prints only the quantity for the ordinary acknowledged row - nothing extra', () => {
    renderQtyCell([worklistRow({ id: 'row-plain', qty: '10', ack_state: 'acknowledged' })]);
    const row = screen.getByTestId('row-row-plain');
    expect(within(row).getByText('10')).toBeInTheDocument();
    expect(within(row).queryByText(/Rejected/)).not.toBeInTheDocument();
    expect(within(row).queryByTestId('board-change-row-plain')).not.toBeInTheDocument();
  });

  it('prints the reason under the qty for a rejected row, with who refused it', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-rejected',
        qty: '12',
        ack_state: 'rejected',
        rejected_by_name: 'Joey Ang',
        rejected_reason: 'No supplier until November',
      }),
    ]);
    const row = screen.getByTestId('row-row-rejected');
    expect(within(row).getByText('12')).toBeInTheDocument();
    expect(
      within(row).getByText('Joey Ang: No supplier until November'),
    ).toBeInTheDocument();
  });

  it('prints "Rejected by <name>" alone when no reason survives', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-rejected-blank',
        qty: '3',
        ack_state: 'rejected',
        rejected_by_name: 'Joey Ang',
        rejected_reason: '   ',
      }),
    ]);
    const row = screen.getByTestId('row-row-rejected-blank');
    expect(within(row).getByText('Rejected by Joey Ang')).toBeInTheDocument();
  });

  it('draws the Was/Now table under the qty for a settled row, off previous_qty alone', () => {
    // Driven by `previous_qty`, NOT `ack_state === 'changed'` (S1): a settle
    // auto-acknowledges the instant it stamps `changed_at` (G4), so the row this cell
    // reads is `acknowledged`, never `changed`, by the time the wire carries it.
    renderQtyCell([
      worklistRow({
        id: 'row-settled',
        qty: '25',
        ack_state: 'acknowledged',
        changed_at: '2026-09-01T10:00:00',
        previous_qty: '10',
        previous_delivery_date: '2026-08-10',
        delivery_date: '2026-09-20',
      }),
    ]);
    const row = screen.getByTestId('row-row-settled');
    // "25" appears twice - the qty cell's own figure and the table's own Now column -
    // which is the point: both read the row's current qty and can never disagree.
    expect(within(row).getAllByText('25').length).toBeGreaterThanOrEqual(2);
    expect(within(row).getByTestId('board-change-row-settled')).toBeInTheDocument();
    expect(within(row).getByText('10')).toBeInTheDocument();
  });

  it('never shows the Was/Now table on a rejected row, even if it once carried a previous value', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-rejected-with-history',
        qty: '4',
        ack_state: 'rejected',
        rejected_by_name: 'Joey Ang',
        rejected_reason: 'No stock',
        previous_qty: '8',
        previous_delivery_date: '2026-08-01',
      }),
    ]);
    const row = screen.getByTestId('row-row-rejected-with-history');
    expect(
      within(row).queryByTestId('board-change-row-rejected-with-history'),
    ).not.toBeInTheDocument();
    expect(within(row).getByText(/No stock/)).toBeInTheDocument();
  });

  it('shows no Was/Now table for a row that has never been settled', () => {
    renderQtyCell([worklistRow({ id: 'row-untouched', qty: '6', ack_state: 'acknowledged' })]);
    const row = screen.getByTestId('row-row-untouched');
    expect(within(row).queryByTestId('board-change-row-untouched')).not.toBeInTheDocument();
  });
});
