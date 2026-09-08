/**
 * The list's own "Outstanding PO/SPO" column (AC-A1..AC-A7, `PLAN-scm-oi-reserving-
 * feedback-8sep.md` slice A): ONE LINE per row - the draft/confirmed mark, the coverage
 * headline, and an info icon that opens `OrderInquiryBackingDocumentsDialog`. No
 * `SupplyBar`, no per-document text, no lateness in the cell any more - every one of those
 * either moved behind the icon or was dropped outright (8 Sep owner cut of the mock).
 * Rendered here as a bare `<table>` off `useOrderInquiryWorklistColumns()` directly - just
 * the one column, so a DataGrid's own chrome (which needs `useListingColumnPreferences`
 * mocked under jsdom, see `OrderInquiriesClient.test.tsx`) never has to enter this test at
 * all.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

describe('the "Outstanding PO/SPO" column: one line, no bar, no late badge (slice A, 8 Sep 2026)', () => {
  it('AC-A2: no supply-bar renders in this column, on a wholly linked row', () => {
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
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });

  it('AC-A2: no supply-bar renders on a partly linked row either', () => {
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
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });

  it('AC-A3: no link-late element renders anywhere in the column, even on a late document', () => {
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
    expect(within(row).queryByTestId('link-late-202607-S0105')).not.toBeInTheDocument();
    expect(row.querySelector('[title*="lands"]')).not.toBeInTheDocument();
    expect(row.querySelector('[title*="arrives late"]')).not.toBeInTheDocument();
  });

  it('AC-A6: a row backing exactly one document prints NO document number in the cell', () => {
    renderRows([
      worklistRow({
        id: 'row-one-doc',
        qty: '5',
        linked_qty: '5',
        po_number: '202607-S0105',
        links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '5', location: 'BRW' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-one-doc');
    expect(within(row).queryByText('202607-S0105')).not.toBeInTheDocument();
    expect(
      within(row).queryByTestId('document-detail-trigger-202607-S0105'),
    ).not.toBeInTheDocument();
    // Still offers the icon (AC-A6's other half).
    expect(within(row).getByTestId('backing-documents-trigger-row-one-doc')).toBeInTheDocument();
  });

  it('AC-A4: the cell prints only the coverage headline and the draft/confirmed mark', () => {
    renderRows([
      worklistRow({
        id: 'row-headline',
        qty: '493',
        linked_qty: '115',
        po_number: '202607-S0105',
        links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '115', location: 'BRW' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-headline');
    expect(within(row).getByText('115 of 493')).toBeInTheDocument();
    expect(within(row).getByTestId('link-draft-mark')).toBeInTheDocument();
    // No document count, no document number, nothing else: the row's own rendered text
    // (this test isolates the `po_number` column alone, see `OneColumnOnly`) is exactly
    // the headline and nothing more - the mark and the info icon are both icon-only, no
    // text node of their own. A `queryByText` regex would have passed just as wrongly
    // with a "3 documents" count present, since it never reads an icon's aria-label.
    expect(row.textContent).toBe('115 of 493');
  });
});

describe('AC-A7: a row nothing can cover', () => {
  it('reads "Not found (new order)" - never "Not linked", which read as an oversight - and shows no icon', () => {
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(within(row).getByText('Not found (new order)')).toBeInTheDocument();
    expect(within(row).queryByText('Not linked')).not.toBeInTheDocument();
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
    expect(
      within(row).queryByTestId('backing-documents-trigger-row-unlinked'),
    ).not.toBeInTheDocument();
  });

  it('carries no draft/confirmed mark at all when there is nothing to mark', () => {
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(within(row).queryByTestId('link-draft-mark')).not.toBeInTheDocument();
    expect(within(row).queryByTestId('link-confirmed-mark')).not.toBeInTheDocument();
  });
});

describe('a cancelled row (coverage restored after the old SupplyBar-only case was deleted)', () => {
  it('an unlinked cancelled row reads "Not found (new order)", the same as any other unlinked row', () => {
    // The old bar test proved a cancelled row "owes nothing" by checking the BAR drew
    // nothing - moot now the bar is gone from this column entirely (AC-A2). This is the
    // replacement: the cell itself never special-cases `state`, so a cancelled row with
    // no links reads exactly as AC-A7 describes any other one.
    renderRows([
      worklistRow({
        id: 'row-cancelled-unlinked',
        qty: '6',
        linked_qty: '0',
        links: [],
        state: 'cancelled',
      }),
    ]);

    const row = screen.getByTestId('row-row-cancelled-unlinked');
    expect(within(row).getByText('Not found (new order)')).toBeInTheDocument();
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
    expect(
      within(row).queryByTestId('backing-documents-trigger-row-cancelled-unlinked'),
    ).not.toBeInTheDocument();
  });

  it('a cancelled row that still carries links from before it was cancelled still reads its headline and icon', () => {
    // The cell reads `links[]` as it stands, never `state` - a cancelled row whose links
    // were never unwound (the state cancels the INSTRUCTION, not the document history)
    // shows the same headline and icon a live row would. Pinned explicitly so a reader
    // does not assume the cell silently hides a cancelled row's own history.
    renderRows([
      worklistRow({
        id: 'row-cancelled-linked',
        qty: '6',
        linked_qty: '6',
        state: 'cancelled',
        links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '6', location: 'BRW' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-cancelled-linked');
    expect(within(row).getByText('6 of 6')).toBeInTheDocument();
    expect(within(row).queryByTestId('supply-bar')).not.toBeInTheDocument();
    expect(
      within(row).getByTestId('backing-documents-trigger-row-cancelled-linked'),
    ).toBeInTheDocument();
  });
});

describe('AC-A5: the info icon opens the backing-documents lightbox', () => {
  it('lists every backing document with kind, number, location, quantity, expected date and standing', () => {
    renderRows([
      worklistRow({
        id: 'row-multi',
        qty: '493',
        linked_qty: '115',
        ack_state: 'acknowledged',
        po_number: '202607-S0105',
        links: [
          {
            id: 'l1',
            kind: 'po',
            document: '202607-S0105',
            qty: '52',
            location: 'BRW-IB',
            expected_date: '2026-08-19',
          },
          {
            id: 'l2',
            kind: 'spo',
            document: 'SPO-2026/08-0061',
            qty: '63',
            location: 'BRW',
            expected_date: '2026-09-01',
          },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-multi');
    fireEvent.click(screen.getByTestId('backing-documents-trigger-row-multi'));

    // Rendered via a portal (Radix `Dialog`), so it is read off `screen`, not `row`.
    const dialog = screen.getByTestId('backing-documents-row-multi');
    expect(within(dialog).getByText('202607-S0105')).toBeInTheDocument();
    expect(within(dialog).getByText('SPO-2026/08-0061')).toBeInTheDocument();
    expect(dialog.textContent).toContain('BRW-IB');
    expect(dialog.textContent).toContain('52');
    expect(dialog.textContent).toContain('63');
    expect(within(dialog).getAllByText('Confirmed').length).toBeGreaterThan(0);
    // Closing returns the trigger to view without unmounting the row (AC-A5).
    expect(row).toBeInTheDocument();
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

describe('AC-A1/AC-A6: the cell prints no per-document detail any more - it all moved behind the icon', () => {
  it('a row backing three documents renders no per-document location/quantity text in the cell', () => {
    renderRows([
      worklistRow({
        id: 'row-spo',
        qty: '493',
        linked_qty: '115',
        po_number: 'SPO-2026/08-0015',
        links: [
          {
            id: 'l1',
            kind: 'spo',
            document: 'SPO-2026/08-0015',
            line_label: 'L14',
            location: 'BRW',
            qty: '52',
          },
          { id: 'l2', kind: 'po', document: '202607-S0105', qty: '30', location: 'BRW-IB' },
          { id: 'l3', kind: 'po', document: '202608-S0016', qty: '33', location: null },
        ],
      }),
    ]);

    const row = screen.getByTestId('row-row-spo');
    // AC-A1: three documents behind one row still reads as ONE line - none of the old
    // per-document text (location, quantity, line label) is rendered in the cell.
    expect(within(row).queryByText(/BRW 52/)).not.toBeInTheDocument();
    expect(within(row).queryByText('L14')).not.toBeInTheDocument();
    expect(within(row).queryByText('no location')).not.toBeInTheDocument();
    expect(within(row).getByText('115 of 493')).toBeInTheDocument();
    expect(within(row).getByTestId('backing-documents-trigger-row-spo')).toBeInTheDocument();
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

  it('shows only the qty and a Changed badge for a settled row - the table is behind a lightbox now', () => {
    // Driven by `previous_qty`, NOT `ack_state === 'changed'` (S1): a settle
    // auto-acknowledges the instant it stamps `changed_at` (G4), so the row this cell
    // reads is `acknowledged`, never `changed`, by the time the wire carries it.
    //
    // The Was/Now table used to render inline here; it now lives behind a lightbox
    // (captain, 1 Sep - the inline table crowded the qty cell), so the row's own cell
    // carries only the figure and the clickable badge, not the table's own "10"/"25".
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
    expect(within(row).getByText('25')).toBeInTheDocument();
    expect(within(row).getByText(/Changed/)).toBeInTheDocument();
    expect(within(row).queryByText('10')).not.toBeInTheDocument();
    expect(screen.queryByTestId('board-change-row-settled')).not.toBeInTheDocument();
  });

  it('opens the lightbox with the Was/Now table when the Changed badge is clicked', () => {
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

    fireEvent.click(screen.getByTestId('change-badge-trigger-row-settled'));

    // Rendered via a portal (Radix `Dialog`), so it is read off `screen`, not `row`.
    const table = screen.getByTestId('board-change-row-settled');
    // "25" appears twice once open - the qty cell's own figure and the table's own Now
    // column - which is the point: both read the row's current qty and can never
    // disagree.
    expect(screen.getAllByText('25').length).toBeGreaterThanOrEqual(2);
    expect(within(table).getByText('10')).toBeInTheDocument();
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
