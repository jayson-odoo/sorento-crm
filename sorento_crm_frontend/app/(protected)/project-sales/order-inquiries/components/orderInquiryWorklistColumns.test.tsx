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
import { fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { describe, expect, it, vi } from 'vitest';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

// AC-D6: Radix Tooltip only mounts TooltipContent's portal on hover, which a plain
// render+query cannot see - mocked to render its children inline instead, the same
// convention `components/rule-builder/RuleBuilder.test.tsx` already uses.
vi.mock('@/components/ui/tooltip', async () => {
  const actual = await vi.importActual<typeof import('@/components/ui/tooltip')>(
    '@/components/ui/tooltip',
  );
  return {
    ...actual,
    TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});
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
  });
  // Said out loud rather than left to `useReactTable` to trip over an `undefined` column
  // def: a test for a column that does not exist yet is a normal red state here, and
  // "Cannot read properties of undefined" names nothing a reader can act on.
  if (!named) throw new Error(`no column with id or accessorKey "${columnId}"`);
  const table = useReactTable({
    data: rows,
    columns: [named],
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            data-testid={`row-${row.original.id}`}
            // Mirrors OrderInquiriesClient.tsx's own `rowClassName` on the real
            // DataGrid (REV-S6/S1, 17 Sep review round): muting is a ROW-level
            // class from the grid itself, not a per-cell wrapper, so this bare
            // `<table>` harness applies it the same way to stay a faithful stand-in.
            className={row.original.redirected_to_pool ? 'opacity-60' : undefined}
          >
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

  it('AC-A6, as the owner reset it on 14 Sep: the cell prints the DOCUMENT NUMBER, and it is the trigger', () => {
    // Superseded by AC-R-26. The 8 Sep cut moved the number behind an info icon; the
    // owner, looking at prod after the 14 Sep upload: "1 column to show the linked PO and
    // 1 column to show the linked SPO ... then I can click on the PO and SPO to view the
    // lightbox popup which is what we currently have". So the number is back in the cell
    // and IS the lightbox trigger - one line still, and one trigger still, which is what
    // the rest of AC-A6 was protecting.
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
    const triggers = within(row).getAllByTestId('backing-documents-trigger-row-one-doc');
    expect(triggers).toHaveLength(1);
    expect(triggers[0].textContent).toBe('202607-S0105');
    expect(
      within(row).queryByTestId('document-detail-trigger-202607-S0105'),
    ).not.toBeInTheDocument();
  });

  it('AC-A4, as the owner reset it on 14 Sep: the cell prints the number and the draft/confirmed mark, and NOT the coverage headline', () => {
    // Superseded by AC-R-26. `115 of 493` is already the lightbox's own subtitle, and the
    // cell has one line to spend: the owner wants it spent on the document number. The
    // one-line proof is unchanged and still the point of this test - the row's own
    // rendered text (this file isolates one column at a time, see `OneColumnOnly`) is
    // exactly the number, so a count or a headline creeping back in fails here.
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
    expect(within(row).queryByText('115 of 493')).not.toBeInTheDocument();
    expect(within(row).getByTestId('link-draft-mark')).toBeInTheDocument();
    expect(row.textContent).toBe('202607-S0105');
  });
});

describe('AC-A7: a row nothing can cover', () => {
  it('reads a plain dash - never "Not found (new order)" or "Not linked" - and shows no icon', () => {
    // S5, AC-D4: "Not found (new order)" read as a caption nobody asked for, and this
    // list has no on-screen explanations - a dash is the whole answer.
    renderRows([worklistRow({ id: 'row-unlinked', qty: '85', linked_qty: '0', links: [] })]);

    const row = screen.getByTestId('row-row-unlinked');
    expect(row.textContent?.trim()).toBe('-');
    expect(within(row).queryByText('Not found (new order)')).not.toBeInTheDocument();
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
  it('an unlinked cancelled row reads a plain dash, the same as any other unlinked row', () => {
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
    expect(row.textContent?.trim()).toBe('-');
    expect(within(row).queryByText('Not found (new order)')).not.toBeInTheDocument();
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
    // The document number, since 14 Sep (AC-R-26); the headline it used to read moved to
    // the lightbox's subtitle. What this test is about is unchanged: a cancelled row reads
    // its own history like any other row.
    expect(within(row).getByText('202607-S0105')).toBeInTheDocument();
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

  it('AC-A13/AC-A14: an SPO entry names its source PO; a PO entry and a sourceless SPO show nothing new', () => {
    // Owner's 9 Sep feedback: "if we link by SPO, where do we see the PO number of this
    // SPO?" - nowhere, before this.
    renderRows([
      worklistRow({
        id: 'row-source-po',
        qty: '493',
        linked_qty: '166',
        ack_state: 'acknowledged',
        links: [
          {
            id: 'l1',
            kind: 'spo',
            document: 'SPO-2026/09-0036',
            qty: '52',
            location: 'BRW',
            source_po_number: '202606-S0110',
          },
          {
            // A PO-kind link never carries this field - shows nothing new.
            id: 'l2',
            kind: 'po',
            document: '202607-S0105',
            qty: '63',
            location: 'BRW-IB',
          },
          {
            // An SPO the book named no source PO for - shows nothing rather than an
            // empty label (AC-A14).
            id: 'l3',
            kind: 'spo',
            document: 'SPO-2026/09-0040',
            qty: '51',
            location: 'BRW',
            source_po_number: null,
          },
        ],
      }),
    ]);

    fireEvent.click(screen.getByTestId('backing-documents-trigger-row-source-po'));
    const dialog = screen.getByTestId('backing-documents-row-source-po');

    expect(within(dialog).getByText('from PO 202606-S0110')).toBeInTheDocument();
    // Exactly one "from PO" line - the sourceless SPO and the PO-kind link add none.
    expect(within(dialog).getAllByText(/^from PO /)).toHaveLength(1);
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
    // The PO column shows the first PO number and how many more there are, since 14 Sep
    // (AC-R-26/AC-R-28) - not the coverage headline it read before.
    expect(within(row).getByText('202607-S0105')).toBeInTheDocument();
    expect(within(row).queryByText('115 of 493')).not.toBeInTheDocument();
    expect(within(row).getByTestId('backing-documents-trigger-row-spo')).toBeInTheDocument();
  });
});

describe('the qty cell: one line, an info icon only when there is something to say (AC-A8..AC-A12, owner feedback 9 Sep 2026 against the running lane)', () => {
  it('AC-A8: a plain acknowledged row is the quantity alone, one line, no icon', () => {
    renderQtyCell([worklistRow({ id: 'row-plain', qty: '10', ack_state: 'acknowledged' })]);
    const row = screen.getByTestId('row-row-plain');
    expect(within(row).getByText('10')).toBeInTheDocument();
    // ONE LINE: the row's own rendered text is exactly the quantity, the same proof
    // AC-A4 uses for the Outstanding column - no icon renders any text of its own.
    expect(row.textContent).toBe('10');
    expect(
      within(row).queryByTestId('qty-annotation-trigger-row-plain'),
    ).not.toBeInTheDocument();
  });

  it('AC-A9: a rejected row shows the quantity and a warning-coloured icon, still one line', () => {
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
    expect(row.textContent).toBe('12');
    const trigger = within(row).getByTestId('qty-annotation-trigger-row-rejected');
    expect(trigger.className).toContain('color-warning-accent');

    fireEvent.click(trigger);
    // Rendered via a portal (Radix `Dialog`), so it is read off `screen`, not `row`.
    const dialog = screen.getByTestId('qty-annotation-row-rejected');
    expect(within(dialog).getByText('Joey Ang: No supplier until November')).toBeInTheDocument();
  });

  it('AC-A9: "Rejected by <name>" alone when no reason survives', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-rejected-blank',
        qty: '3',
        ack_state: 'rejected',
        rejected_by_name: 'Joey Ang',
        rejected_reason: '   ',
      }),
    ]);
    fireEvent.click(screen.getByTestId('qty-annotation-trigger-row-rejected-blank'));
    const dialog = screen.getByTestId('qty-annotation-row-rejected-blank');
    expect(within(dialog).getByText('Rejected by Joey Ang')).toBeInTheDocument();
  });

  it('AC-A10: a settled row shows the quantity and a MUTED icon, still one line', () => {
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
    expect(row.textContent).toBe('25');
    const trigger = within(row).getByTestId('qty-annotation-trigger-row-settled');
    expect(trigger.className).not.toContain('color-warning-accent');
    expect(trigger.className).toContain('text-muted-foreground');
  });

  it('AC-A10: opens the dialog with the Was/Now table when the icon is clicked', () => {
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

    fireEvent.click(screen.getByTestId('qty-annotation-trigger-row-settled'));

    const dialog = screen.getByTestId('qty-annotation-row-settled');
    const table = within(dialog).getByTestId('board-change-row-settled');
    // "25" appears twice once open - the qty cell's own figure and the table's own Now
    // column - which is the point: both read the row's current qty and can never
    // disagree.
    expect(screen.getAllByText('25').length).toBeGreaterThanOrEqual(2);
    expect(within(table).getByText('10')).toBeInTheDocument();
  });

  it('AC-A11: a row rejected after once being changed carries BOTH facts in the dialog', () => {
    // The old rule let a rejection hide a row's change history from the reader entirely
    // ("never shows the Was/Now table on a rejected row"). Tucked behind an icon rather
    // than crowding the cell, there is no reason to keep hiding it - both facts show.
    renderQtyCell([
      worklistRow({
        id: 'row-rejected-with-history',
        qty: '4',
        ack_state: 'rejected',
        rejected_by_name: 'Joey Ang',
        rejected_reason: 'No stock',
        changed_at: '2026-08-05T09:00:00',
        previous_qty: '8',
        previous_delivery_date: '2026-08-01',
      }),
    ]);
    const row = screen.getByTestId('row-row-rejected-with-history');
    expect(row.textContent).toBe('4');
    const trigger = within(row).getByTestId(
      'qty-annotation-trigger-row-rejected-with-history',
    );
    // Both apply: the warning colour wins, a rejection being the more urgent fact.
    expect(trigger.className).toContain('color-warning-accent');

    fireEvent.click(trigger);
    const dialog = screen.getByTestId('qty-annotation-row-rejected-with-history');
    expect(within(dialog).getByText(/No stock/)).toBeInTheDocument();
    expect(
      within(dialog).getByTestId('board-change-row-rejected-with-history'),
    ).toBeInTheDocument();
  });

  it('AC-A8: shows no icon for a row that has never been rejected or settled', () => {
    renderQtyCell([worklistRow({ id: 'row-untouched', qty: '6', ack_state: 'acknowledged' })]);
    const row = screen.getByTestId('row-row-untouched');
    expect(row.textContent).toBe('6');
    expect(
      within(row).queryByTestId('qty-annotation-trigger-row-untouched'),
    ).not.toBeInTheDocument();
  });
});

describe('a bundled row (PLAN-scm-supplied-with-companions.md S5, UAC D1-D3/D10)', () => {
  it('D1: fully bundled, host on a PO reads "Included with <host> · <host coverage>"', () => {
    renderRows([
      worklistRow({
        id: 'host-row',
        item_code: 'CKS1050',
        qty: '1',
        linked_qty: '1',
        links: [{ id: 'l1', kind: 'po', document: '202609-S0105', qty: '1' }],
      }),
      worklistRow({
        id: 'companion-row',
        item_code: 'CKSW015',
        qty: '1',
        linked_qty: '0',
        links: [],
        bundled_qty: '1',
        bundled_with: {
          row_id: 'host-row',
          item_code: 'CKS1050',
          item_codes: ['CKS1050'],
          anchor_headline: '1 of 1',
        },
      }),
    ]);

    const row = screen.getByTestId('row-companion-row');
    expect(within(row).getByTitle('Included with CKS1050 · 1 of 1')).toBeInTheDocument();
    // The info icon opens the ANCHOR row's own lightbox - it exists for this row.
    expect(within(row).getByTestId('backing-documents-trigger-companion-row')).toBeInTheDocument();
  });

  it('D2: fully bundled, host not found reads "Included with <host> · Nothing linked yet"', () => {
    renderRows([
      worklistRow({ id: 'host-row-2', item_code: 'CKS1050', qty: '1', linked_qty: '0', links: [] }),
      worklistRow({
        id: 'companion-row-2',
        item_code: 'CKSW015',
        qty: '1',
        linked_qty: '0',
        links: [],
        bundled_qty: '1',
        bundled_with: {
          row_id: 'host-row-2',
          item_code: 'CKS1050',
          item_codes: ['CKS1050'],
          anchor_headline: null,
        },
      }),
    ]);

    const row = screen.getByTestId('row-companion-row-2');
    expect(
      within(row).getByTitle('Included with CKS1050 · Nothing linked yet'),
    ).toBeInTheDocument();
  });

  it('D3: partly bundled reads "<bundled> with <host> · <own linked> of <ala carte remainder>"', () => {
    renderRows([
      worklistRow({
        id: 'host-row-3',
        item_code: 'CKS1050',
        qty: '1',
        linked_qty: '1',
        links: [{ id: 'l3', kind: 'po', document: '202609-S0110', qty: '1' }],
      }),
      worklistRow({
        id: 'companion-row-3',
        item_code: 'CKSW015',
        qty: '3',
        linked_qty: '0',
        links: [],
        bundled_qty: '1',
        bundled_with: {
          row_id: 'host-row-3',
          item_code: 'CKS1050',
          item_codes: ['CKS1050'],
          anchor_headline: '1 of 1',
        },
      }),
    ]);

    const row = screen.getByTestId('row-companion-row-3');
    // qty 3, bundled 1: the ala carte remainder is 2, and none of it is linked yet.
    expect(within(row).getByTitle('1 with CKS1050 · 0 of 2')).toBeInTheDocument();
  });

  it('D10: a pair rule, fully bundled, reads "Included with N items" - never the word "host"', () => {
    renderRows([
      worklistRow({
        id: 'host-x',
        item_code: 'X',
        qty: '2',
        linked_qty: '2',
        links: [{ id: 'lx', kind: 'po', document: '202609-S0120', qty: '2' }],
      }),
      worklistRow({
        id: 'host-y',
        item_code: 'Y',
        qty: '2',
        linked_qty: '2',
        links: [{ id: 'ly', kind: 'po', document: '202609-S0120', qty: '2' }],
      }),
      worklistRow({
        id: 'companion-sc',
        item_code: 'SC',
        qty: '2',
        linked_qty: '0',
        links: [],
        bundled_qty: '2',
        // The FIRST host named on the rule is the anchor (plan 3.2) - X here.
        bundled_with: {
          row_id: 'host-x',
          item_code: 'X',
          item_codes: ['X', 'Y'],
          anchor_headline: '2 of 2',
        },
      }),
    ]);

    const row = screen.getByTestId('row-companion-sc');
    expect(within(row).getByTitle('Included with 2 items · 2 of 2')).toBeInTheDocument();
    expect(row.textContent?.toLowerCase()).not.toContain('host');
  });
});

describe('AC-D6: the instruction column tooltip prints the reallocation note in words', () => {
  it('renders "Found: PO-A 34" for a row the reallocation cascade linked', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-reallocated',
          qty: '34',
          verb: 'ORDER',
          note: 'Found: PO-A 34',
        }),
      ],
      'verb',
    );

    const row = screen.getByTestId('row-row-reallocated');
    expect(within(row).getByText('Found: PO-A 34')).toBeInTheDocument();
  });
});

/**
 * Slice S3 (`PLAN-scm-oi-sheet-pairing-repair.md` section 6, owner ruling 14 Sep 2026 off a
 * live look at prod after the upload): "1 column to show the linked PO and 1 column to show
 * the linked SPO (if linked to more than 1 then put as +1 pill), I want all rows to have 1
 * line only, then I can click on the PO and SPO to view the lightbox popup which is what we
 * currently have."
 *
 * So the `po_number` column keeps its id - a saved column layout is keyed by it - loses the
 * coverage headline and the info icon, and prints the first PO number as the lightbox
 * trigger; a new `spo_number` column does the same for the shipping orders beside it.
 */

/**
 * What an empty cell reads. The plan says "a muted dash", and this pins the ASCII hyphen:
 * every en dash and em dash is out across this repository, in code and in writing alike, so
 * a coder reaching for a typographic one would be breaking a standing rule to satisfy a
 * test. One character to change here if the owner wants another placeholder.
 */
const MUTED_DASH = '-';

/** The raw column defs, for the shape assertions AC-R-31 makes about them. */
function columnDefs() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result } = renderHook(() => useOrderInquiryWorklistColumns(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  return result.current as Array<
    ColumnDef<OrderInquiryWorklistRow> & {
      id?: string;
      size?: number;
      meta?: { headerTitle?: string };
    }
  >;
}

// Owner alignment markup, 17 Sep (SECOND round on the same day): words, not icons.
// Each mark is ONE short word rendered as the existing muted PILL style (`via PO`'s own
// `text-2xs text-muted-foreground` span, now a clickable button) - `received` /
// `reallocate` / `unlink` / `used` / `note` - clicking the word opens the lightbox. RED
// against the CURRENT build (still icon-shaped with no visible word for most of these,
// and `repoint` where `reallocate` belongs) - grepped this file for the literal strings
// "redirected" and "received" as visible cell text before writing these; every
// remaining "redirected" occurrence below is a `queryByText`/`not.toMatch` guard, never
// an assertion that it renders.
describe('AC-RL-02 (`PLAN-oi-replan-received-links.md` S1, 17 Sep rulings): a received document is the word "received", one muted pill', () => {
  it('a received link shows the word "received" as a muted pill, and clicking it opens the dialog reading "Received 158 of 158" for it and nothing for an open link', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-mixed',
          qty: '182',
          linked_qty: '178',
          links: [
            {
              id: 'l1',
              kind: 'spo',
              document: 'SPO-2026/01-0143',
              qty: '158',
              location: 'BRW-IR',
              received: true,
              received_qty: '158',
            },
            {
              id: 'l2',
              kind: 'po',
              document: '202607-S0105',
              qty: '20',
              location: 'BRW-IB',
              received: false,
              received_qty: '0',
            },
          ],
        }),
      ],
      'spo_number',
    );

    const row = screen.getByTestId('row-row-mixed');
    const mark = within(row).getByTestId('backing-documents-received-spo-row-mixed');
    expect(mark.textContent).toBe('received');
    // One line: no block-level child hides the row height.
    expect(row.querySelectorAll('div')).toHaveLength(0);

    fireEvent.click(mark);
    const dialog = screen.getByTestId('backing-documents-row-mixed');
    expect(within(dialog).getByText('Received 158 of 158')).toBeInTheDocument();
    expect(within(dialog).queryByText(/Received 20/)).not.toBeInTheDocument();
  });

  it('an OPEN link carries no "received" pill', () => {
    renderRows([
      worklistRow({
        id: 'row-open',
        qty: '40',
        linked_qty: '40',
        po_number: '202607-S0105',
        links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '40' }],
      }),
    ]);

    const row = screen.getByTestId('row-row-open');
    expect(
      within(row).queryByTestId('backing-documents-received-row-open'),
    ).not.toBeInTheDocument();
    expect(within(row).queryByText('received')).not.toBeInTheDocument();
  });
});

describe('AC-RL-04 (`PLAN-oi-replan-received-links.md` S3, 17 Sep rulings): a redirected row reads "used", never "redirected"', () => {
  it('a redirected row carries the word "used" as a muted pill on its Qty cell, no visible "redirected" text anywhere, and clicking it opens the Qty annotation lightbox showing the note', () => {
    renderQtyCell([
      worklistRow({
        id: 'row-redirected',
        qty: '182',
        ack_state: 'acknowledged',
        redirected_to_pool: true,
        note:
          'SPO-2026/01-0143 received 19 Jan 2026 into BRW-IR, used by earlier orders. ' +
          'Bought again at revision 4: see the new row',
      }),
    ]);

    const row = screen.getByTestId('row-row-redirected');
    expect(within(row).getByText('182')).toBeInTheDocument();
    // The word "redirected" must not appear anywhere in the rendered row (17 Sep
    // ruling) - text nodes only, so this only passes once the OLD literal mark is gone.
    expect(row.textContent ?? '').not.toMatch(/redirected/i);

    const mark = within(row).getByTestId('qty-annotation-trigger-row-redirected');
    expect(mark.textContent).toBe('used');
    expect(row.querySelectorAll('div')).toHaveLength(0);

    fireEvent.click(mark);
    const dialog = screen.getByTestId('qty-annotation-row-redirected');
    expect(
      within(dialog).getByText(
        'SPO-2026/01-0143 received 19 Jan 2026 into BRW-IR, used by earlier orders. ' +
          'Bought again at revision 4: see the new row',
      ),
    ).toBeInTheDocument();
  });

  it('an ordinary row carries no "used" pill', () => {
    renderQtyCell([
      worklistRow({ id: 'row-plain-2', qty: '10', ack_state: 'acknowledged' }),
    ]);

    const row = screen.getByTestId('row-row-plain-2');
    expect(
      within(row).queryByTestId('qty-annotation-trigger-row-plain-2'),
    ).not.toBeInTheDocument();
    expect(within(row).queryByText('used')).not.toBeInTheDocument();
  });
});

describe('AC-RL-24 (`PLAN-oi-replan-received-links.md` S1b, 17 Sep rulings): the word "reallocate" or "unlink", a lightbox listing every candidate', () => {
  it('a REALLOCATE suggestion shows the word "reallocate" as a muted amber pill, and clicking it opens a lightbox listing every candidate earliest first with the footer instruction - never the word "repoint"', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-reallocate',
          qty: '158',
          linked_qty: '158',
          item_code: 'B2154-NL',
          links: [
            {
              id: 'l1',
              kind: 'spo',
              document: 'SPO-2026/01-0143',
              qty: '158',
              location: 'BRW-IR',
              expected_date: '2026-09-01',
              suggestion: {
                kind: 'reallocate',
                candidates: [
                  {
                    inquiry_no: 'OI-000539', item_code: 'CB2805A-DIY',
                    so_number: 'SO420100', delivery_date: '2026-12-01', open_qty: '90',
                  },
                  {
                    inquiry_no: 'OI-000540', item_code: 'CB2805A-DIY',
                    so_number: 'SO420200', delivery_date: '2027-01-15', open_qty: '300',
                  },
                ],
              },
            },
          ],
        }),
      ],
      'spo_number',
    );

    const row = screen.getByTestId('row-row-reallocate');
    const mark = within(row).getByTestId('backing-documents-suggestion-spo-row-reallocate');
    expect(mark.textContent).toBe('reallocate');
    expect(within(row).queryByText('repoint')).not.toBeInTheDocument();
    expect(row.querySelectorAll('div')).toHaveLength(0);

    fireEvent.click(mark);
    const lightbox = screen.getByTestId('link-suggestion-row-reallocate');
    // Headed by the document, item and quantity.
    expect(within(lightbox).getByText('SPO-2026/01-0143')).toBeInTheDocument();
    expect(within(lightbox).getByText(/B2154-NL/)).toBeInTheDocument();
    // Candidates earliest first, the first marked "Reallocate to", the rest plain -
    // never "Repoint to" anywhere in the lightbox.
    expect(
      within(lightbox).getByText(
        'Reallocate to OI-000539 · SO420100 · needed 01/12/2026 · open 90',
      ),
    ).toBeInTheDocument();
    expect(
      within(lightbox).getByText('OI-000540 · SO420200 · needed 15/01/2027 · open 300'),
    ).toBeInTheDocument();
    expect(within(lightbox).queryByText(/repoint/i)).not.toBeInTheDocument();
    expect(
      within(lightbox).getByText(
        'Re-key the line to the chosen sales order in AutoCount; the link moves at the next upload',
      ),
    ).toBeInTheDocument();
  });

  it('an UNLINK suggestion shows the word "unlink" as a muted amber pill, and clicking it opens a lightbox reading "Unlink · no sooner inquiry needs this item"', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-unlink',
          qty: '80',
          linked_qty: '80',
          links: [
            {
              id: 'l1', kind: 'po', document: '202607-S0105', qty: '80',
              suggestion: { kind: 'unlink' },
            },
          ],
        }),
      ],
      'po_number',
    );

    const row = screen.getByTestId('row-row-unlink');
    const mark = within(row).getByTestId('backing-documents-suggestion-row-unlink');
    expect(mark.textContent).toBe('unlink');
    expect(row.querySelectorAll('div')).toHaveLength(0);

    fireEvent.click(mark);
    const lightbox = screen.getByTestId('link-suggestion-row-unlink');
    expect(
      within(lightbox).getByText('Unlink · no sooner inquiry needs this item'),
    ).toBeInTheDocument();
  });

  it('a link with NO suggestion carries neither pill', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-no-suggestion',
          qty: '40',
          linked_qty: '40',
          links: [{ id: 'l1', kind: 'po', document: '202607-S0110', qty: '40', suggestion: null }],
        }),
      ],
      'po_number',
    );

    const row = screen.getByTestId('row-row-no-suggestion');
    expect(
      within(row).queryByTestId('backing-documents-suggestion-row-no-suggestion'),
    ).not.toBeInTheDocument();
    expect(within(row).queryByText('reallocate')).not.toBeInTheDocument();
    expect(within(row).queryByText('unlink')).not.toBeInTheDocument();
  });
});

describe('AC-RL-46 (`PLAN-oi-replan-received-links.md` S5, 17 Sep rulings): the move note reaches the existing Qty annotation dialog via the word "note"', () => {
  it('a row AutoCount moved a document off - now carrying no links - renders the word "note" as a muted pill, and clicking it shows the move note', () => {
    // Reuses the SAME affordance rejected/settled/redirected rows already use
    // (`OrderInquiryQtyAnnotationDialog` / `qty-annotation-trigger-<id>`) - never a new
    // trigger on `OrderInquiryBackingDocumentsDialog`. This row is neither rejected nor
    // carries a `previous_qty` nor `redirected_to_pool` (a settle never touched it, and
    // it was not itself the redirected row - it is AC-RL-40's row A after a book move),
    // so today's trigger condition (`rejected || changed`) has no reason to fire at all.
    renderQtyCell([
      worklistRow({
        id: 'row-moved',
        qty: '90',
        ack_state: 'acknowledged',
        links: [],
        note: 'AutoCount moved 202607-S0077 to SO314595',
      }),
    ]);

    const row = screen.getByTestId('row-row-moved');
    const mark = within(row).getByTestId('qty-annotation-trigger-row-moved');
    expect(mark.textContent).toBe('note');

    fireEvent.click(mark);
    const dialog = screen.getByTestId('qty-annotation-row-moved');
    expect(within(dialog).getByText('AutoCount moved 202607-S0077 to SO314595')).toBeInTheDocument();
  });
});

describe('the PO and SPO columns (S3, owner 14 Sep 2026)', () => {
  it('AC-R-26/AC-D4: one PO link prints that number as the trigger, with no pill and no headline, and the SPO cell reads "awaiting shipment"', () => {
    const row = worklistRow({
      id: 'row-one-po',
      qty: '5',
      linked_qty: '5',
      po_number: '202607-S0105',
      links: [{ id: 'l1', kind: 'po', document: '202607-S0105', qty: '5', location: 'BRW' }],
    });

    const po = renderRows([row]);
    const poCell = screen.getByTestId('row-row-one-po');
    const triggers = within(poCell).getAllByTestId('backing-documents-trigger-row-one-po');
    expect(triggers).toHaveLength(1);
    expect(triggers[0].textContent).toBe('202607-S0105');
    // One line, and only the number on it: no coverage headline, no document count, and no
    // second trigger left over from the info icon the number replaces.
    expect(poCell.textContent).toBe('202607-S0105');
    expect(within(poCell).queryByText('5 of 5')).not.toBeInTheDocument();
    expect(within(poCell).queryByText(/^\+\d+$/)).not.toBeInTheDocument();
    po.unmount();

    // S5, AC-D4: bought but not yet on a shipment reads "awaiting shipment", distinct
    // from the plain dash a row with no link at all gets.
    renderRows([row], 'spo_number');
    const spoCell = screen.getByTestId('row-row-one-po');
    expect(within(spoCell).getByText('awaiting shipment')).toBeInTheDocument();
    expect(
      within(spoCell).queryByTestId('backing-documents-trigger-spo-row-one-po'),
    ).not.toBeInTheDocument();
  });

  it('AC-R-27: two links on ONE shipping order print that number once, with no pill', () => {
    // The pill counts DISTINCT document numbers, not links. A shipping order that states
    // this row's product on two containers is still one document to click on, and "+1"
    // beside it would be the screen inventing a second one.
    const row = worklistRow({
      id: 'row-two-links',
      qty: '50',
      linked_qty: '50',
      links: [
        { id: 'l1', kind: 'spo', document: 'SPO-2026/08-0061', qty: '30', location: 'BRW' },
        { id: 'l2', kind: 'spo', document: 'SPO-2026/08-0061', qty: '20', location: 'BRW' },
        { id: 'l3', kind: 'po', document: '202607-S0105', qty: '50', location: 'BRW-IB' },
      ],
    });

    const spo = renderRows([row], 'spo_number');
    const spoCell = screen.getByTestId('row-row-two-links');
    expect(within(spoCell).getAllByText('SPO-2026/08-0061')).toHaveLength(1);
    expect(within(spoCell).queryByText(/^\+\d+$/)).not.toBeInTheDocument();
    expect(
      within(spoCell).getByTestId('backing-documents-trigger-spo-row-two-links').textContent,
    ).toBe('SPO-2026/08-0061');
    spo.unmount();

    renderRows([row]);
    const poCell = screen.getByTestId('row-row-two-links');
    expect(
      within(poCell).getByTestId('backing-documents-trigger-row-two-links').textContent,
    ).toBe('202607-S0105');
  });

  it('AC-R-28: three shipping orders print the first and a +2 pill, and the number or the pill opens the lightbox', () => {
    // Two rows carrying the same links, so both halves of "either opens it" are asserted
    // in one render: one dialog per row, addressed by the row's own id.
    const links = [
      { id: 'l1', kind: 'spo' as const, document: 'SPO-2026/08-0061', qty: '20', location: 'BRW' },
      { id: 'l2', kind: 'spo' as const, document: 'SPO-2026/09-0036', qty: '20', location: 'BRW' },
      { id: 'l3', kind: 'spo' as const, document: 'SPO-2026/09-0040', qty: '10', location: 'BRW' },
    ];
    renderRows(
      [
        worklistRow({ id: 'row-a', qty: '50', linked_qty: '50', links }),
        worklistRow({ id: 'row-b', qty: '50', linked_qty: '50', links }),
      ],
      'spo_number',
    );

    const first = screen.getByTestId('row-row-a');
    expect(within(first).getByTestId('backing-documents-trigger-spo-row-a').textContent).toBe(
      'SPO-2026/08-0061',
    );
    expect(within(first).getByText('+2')).toBeInTheDocument();
    expect(within(first).queryByText('SPO-2026/09-0036')).not.toBeInTheDocument();

    fireEvent.click(within(first).getByTestId('backing-documents-trigger-spo-row-a'));
    // Rendered via a portal (Radix `Dialog`), so it is read off `screen`, not the row.
    const fromNumber = screen.getByTestId('backing-documents-row-a');
    expect(within(fromNumber).getByText('SPO-2026/08-0061')).toBeInTheDocument();
    expect(within(fromNumber).getByText('SPO-2026/09-0036')).toBeInTheDocument();
    expect(within(fromNumber).getByText('SPO-2026/09-0040')).toBeInTheDocument();

    const second = screen.getByTestId('row-row-b');
    fireEvent.click(within(second).getByText('+2'));
    const fromPill = screen.getByTestId('backing-documents-row-b');
    expect(within(fromPill).getByText('SPO-2026/09-0040')).toBeInTheDocument();
  });

  it('AC-D4/AC-R-29: a row with no links reads a dash in BOTH the PO and the SPO column, and nothing is clickable', () => {
    const row = worklistRow({ id: 'row-none', qty: '85', linked_qty: '0', links: [] });

    const po = renderRows([row]);
    const poCell = screen.getByTestId('row-row-none');
    expect(poCell.textContent?.trim()).toBe(MUTED_DASH);
    expect(within(poCell).queryByText('Not found (new order)')).not.toBeInTheDocument();
    expect(within(poCell).queryByRole('button')).not.toBeInTheDocument();
    po.unmount();

    renderRows([row], 'spo_number');
    const spoCell = screen.getByTestId('row-row-none');
    expect(spoCell.textContent?.trim()).toBe(MUTED_DASH);
    expect(within(spoCell).queryByRole('button')).not.toBeInTheDocument();
  });

  it('AC-D4: a row on a PO with no shipment yet reads "awaiting shipment" in the SPO column', () => {
    const row = worklistRow({
      id: 'row-po-only',
      qty: '10',
      linked_qty: '10',
      links: [{ id: 'l1', kind: 'po', document: '202605-S0009', qty: '10' }],
    });

    renderRows([row], 'spo_number');

    const spoCell = screen.getByTestId('row-row-po-only');
    expect(within(spoCell).getByText('awaiting shipment')).toBeInTheDocument();
    expect(within(spoCell).queryByRole('button')).not.toBeInTheDocument();
  });

  it('AC-D1/R-E: a PO link whose PO also carries a derived SPO reads that SPO number tagged "via PO"', () => {
    const row = worklistRow({
      id: 'row-derived-spo',
      qty: '10',
      linked_qty: '10',
      links: [
        { id: 'l1', kind: 'po', document: '202605-S0009', qty: '10' },
        {
          id: 'l2',
          kind: 'spo',
          document: 'SPO-2026/07-0005',
          qty: '5',
          derived: true,
        },
      ],
    });

    renderRows([row], 'spo_number');

    const spoCell = screen.getByTestId('row-row-derived-spo');
    expect(
      within(spoCell).getByTestId('backing-documents-trigger-spo-row-derived-spo'),
    ).toHaveTextContent('SPO-2026/07-0005');
    expect(
      within(spoCell).getByTestId('backing-documents-via-spo-row-derived-spo'),
    ).toHaveTextContent('via PO');
  });

  it('AC-D3/R-E: an SPO link carrying source_po_number reads that PO number tagged "via SPO"', () => {
    const row = worklistRow({
      id: 'row-spo-with-source',
      qty: '6',
      linked_qty: '6',
      links: [
        {
          id: 'l1',
          kind: 'spo',
          document: 'SPO-2026/07-0006',
          qty: '6',
          source_po_number: 'ZZT-SOURCE-PO-0099',
          derived_po: true,
        },
      ],
    });

    renderRows([row]);

    const poCell = screen.getByTestId('row-row-spo-with-source');
    expect(
      within(poCell).getByTestId('backing-documents-trigger-row-spo-with-source'),
    ).toHaveTextContent('ZZT-SOURCE-PO-0099');
    expect(
      within(poCell).getByTestId('backing-documents-via-row-spo-with-source'),
    ).toHaveTextContent('via SPO');
  });

  it('AC-R-30: a bundled row keeps the PO cell it reads today, and its SPO cell is a dash', () => {
    // The D1 fixture verbatim (`PLAN-scm-supplied-with-companions.md` S5): a companion that
    // rides entirely inside its host has no documents of its own, and the new columns must
    // not disturb what that cell already says.
    const rows = [
      worklistRow({
        id: 'host-row',
        item_code: 'CKS1050',
        qty: '1',
        linked_qty: '1',
        links: [{ id: 'l1', kind: 'po', document: '202609-S0105', qty: '1' }],
      }),
      worklistRow({
        id: 'companion-row',
        item_code: 'CKSW015',
        qty: '1',
        linked_qty: '0',
        links: [],
        bundled_qty: '1',
        bundled_with: {
          row_id: 'host-row',
          item_code: 'CKS1050',
          item_codes: ['CKS1050'],
          anchor_headline: '1 of 1',
        },
      }),
    ];

    const po = renderRows(rows);
    const poCell = screen.getByTestId('row-companion-row');
    expect(within(poCell).getByTitle('Included with CKS1050 · 1 of 1')).toBeInTheDocument();
    expect(
      within(poCell).getByTestId('backing-documents-trigger-companion-row'),
    ).toBeInTheDocument();
    po.unmount();

    renderRows(rows, 'spo_number');
    const spoCell = screen.getByTestId('row-companion-row');
    expect(spoCell.textContent?.trim()).toBe(MUTED_DASH);
    expect(
      within(spoCell).queryByTestId('backing-documents-trigger-spo-companion-row'),
    ).not.toBeInTheDocument();
  });

  it('AC-R-35: the PO cell names the purchase order behind a shipment, and names it once', () => {
    // Plan 7.2, owner 14 Sep evening: "we definitely cannot double count, but by this
    // linking it helps us to know the PO and SPO corresponding to this order inquiry".
    // The importer stops linking a purchase order line for units already on its own ship,
    // so a row whose whole quantity has sailed holds no `po` link at all - and the PO
    // column would go blank on exactly the rows purchasing most wants to trace. It reads
    // the `source_po_number` the SPO link already carries instead.
    const shipped = worklistRow({
      id: 'row-shipped',
      qty: '62',
      linked_qty: '62',
      links: [
        {
          id: 'l1',
          kind: 'spo',
          document: 'SPO-2026/04-0043',
          qty: '62',
          location: 'BRW',
          source_po_number: '202510-S0078',
        },
      ],
    });

    const po = renderRows([shipped]);
    const poCell = screen.getByTestId('row-row-shipped');
    const trigger = within(poCell).getByTestId('backing-documents-trigger-row-shipped');
    expect(trigger.textContent).toBe('202510-S0078');
    expect(within(poCell).queryByText(MUTED_DASH)).not.toBeInTheDocument();
    expect(within(poCell).queryByText(/^\+\d+$/)).not.toBeInTheDocument();
    // The same lightbox the SPO number opens - one row, one set of backing documents.
    fireEvent.click(trigger);
    const dialog = screen.getByTestId('backing-documents-row-shipped');
    expect(within(dialog).getByText('SPO-2026/04-0043')).toBeInTheDocument();
    po.unmount();

    renderRows([shipped], 'spo_number');
    expect(
      within(screen.getByTestId('row-row-shipped')).getByTestId(
        'backing-documents-trigger-spo-row-shipped',
      ).textContent,
    ).toBe('SPO-2026/04-0043');
  });

  it('AC-R-35: a purchase order and its own shipment are ONE number in the PO cell', () => {
    // The partly shipped case: 40 of the 62 sailed, so the row holds a `po` link for the
    // 22 that did not AND an `spo` link whose source is that same purchase order. One
    // document, named once - a `+1` pill here would be the screen inventing a second
    // purchase order out of the two halves of one.
    renderRows([
      worklistRow({
        id: 'row-part-shipped',
        qty: '62',
        linked_qty: '62',
        links: [
          { id: 'l1', kind: 'spo', document: 'SPO-2026/04-0043', qty: '40',
            source_po_number: '202510-S0078' },
          { id: 'l2', kind: 'po', document: '202510-S0078', qty: '22' },
        ],
      }),
    ]);

    const poCell = screen.getByTestId('row-row-part-shipped');
    expect(within(poCell).getAllByText('202510-S0078')).toHaveLength(1);
    expect(within(poCell).queryByText(/^\+\d+$/)).not.toBeInTheDocument();
    expect(
      within(poCell).getByTestId('backing-documents-trigger-row-part-shipped').textContent,
    ).toBe('202510-S0078');
  });

  it('AC-R-31: the two columns carry the ids, header titles and explicit sizes a saved layout keys on', () => {
    const columns = columnDefs();
    const po = columns.find((column) => column.id === 'po_number');
    const spo = columns.find((column) => column.id === 'spo_number');

    expect(po, 'the po_number column must keep its id - saved layouts are keyed by it').toBeDefined();
    expect(spo, 'the spo_number column is missing').toBeDefined();
    expect(po?.meta?.headerTitle).toBe('PO');
    expect(spo?.meta?.headerTitle).toBe('SPO');
    // `tableLayout: { width: 'fixed' }` is this listing's contract, so a column with no
    // size of its own takes whatever is left and the row stops being one line.
    expect(typeof po?.size).toBe('number');
    expect(typeof spo?.size).toBe('number');
    // Side by side, SPO immediately after PO (section 6).
    expect(columns.indexOf(spo!)).toBe(columns.indexOf(po!) + 1);
  });
});

describe('AC-RL-04 amended (17 Sep review round): a redirected row is visually muted, and the lightbox never says "Redirected"', () => {
  it('a redirected_to_pool row is muted the same way this table already mutes an inactive row - opacity-60 on the row itself', () => {
    // No `state === 'cancelled'` styling exists anywhere in this file (the checkbox's
    // own `disabledReason` at the select column is the only `state` read at all, and a
    // cancelled row's OTHER cells read as plain, unmuted text - see the "coverage
    // restored" describe block above). `opacity-60` is this codebase's own convention
    // for a row that is no longer active. In the real listing (OrderInquiriesClient.tsx)
    // this comes from the DataGrid's own `rowClassName` on the ROW - a per-cell wrapper
    // (`display: contents`) has no box, so `opacity-60` on it never applies - so this
    // pins the row's own className, not a cell's.
    renderRows(
      [
        worklistRow({
          id: 'row-redirected-muted',
          qty: '182',
          item_code: 'B2154-NL',
          redirected_to_pool: true,
        }),
      ],
      'item_code',
    );
    const itemCodeRow = screen.getByTestId('row-row-redirected-muted');
    expect(itemCodeRow.className).toContain('opacity-60');

    renderQtyCell([
      worklistRow({
        id: 'row-redirected-muted-2',
        qty: '182',
        redirected_to_pool: true,
      }),
    ]);
    const qtyRow = screen.getByTestId('row-row-redirected-muted-2');
    expect(qtyRow.className).toContain('opacity-60');
  });

  it('an ordinary (not redirected) row carries no opacity-60 on itself', () => {
    renderRows(
      [worklistRow({ id: 'row-plain-muted-check', qty: '10', item_code: 'B2154-NL' })],
      'item_code',
    );
    const row = screen.getByTestId('row-row-plain-muted-check');
    expect(row.className).not.toContain('opacity-60');
  });

  it('the open Qty annotation lightbox for a "used" row never contains the text "Redirected" anywhere in document.body, and shows "Used"', () => {
    // `OrderInquiryQtyAnnotationDialog`'s own `DialogDescription` reads the literal word
    // "Redirected" for exactly this row shape (`redirected && !rejected && !previous`) -
    // the row-level check at AC-RL-04's own test above only reads `row.textContent`, a
    // scope that never reaches the dialog's portal content at all.
    renderQtyCell([
      worklistRow({
        id: 'row-redirected-dialog',
        qty: '182',
        ack_state: 'acknowledged',
        redirected_to_pool: true,
        note: 'SPO-2026/01-0143 received 19 Jan 2026 into BRW-IR, used by earlier orders',
      }),
    ]);
    const row = screen.getByTestId('row-row-redirected-dialog');
    fireEvent.click(within(row).getByTestId('qty-annotation-trigger-row-redirected-dialog'));

    const dialog = screen.getByTestId('qty-annotation-row-redirected-dialog');
    expect(dialog.textContent ?? '').not.toMatch(/redirected/i);
    expect(document.body.textContent ?? '').not.toMatch(/redirected/i);
    expect(within(dialog).getByText('Used')).toBeInTheDocument();
  });

  it('for a "note" (AutoCount move) row, the lightbox section heading reads "Moved by AutoCount", never "Redirected"', () => {
    // `MovedSection`'s `<h3>` is shared by BOTH callers today and always prints
    // "Redirected", even for AC-RL-46's own AutoCount-move row, which is neither
    // rejected, changed nor `redirected_to_pool` at all.
    renderQtyCell([
      worklistRow({
        id: 'row-moved-heading',
        qty: '90',
        ack_state: 'acknowledged',
        links: [],
        note: 'AutoCount moved 202607-S0077 to SO314595',
      }),
    ]);
    const row = screen.getByTestId('row-row-moved-heading');
    fireEvent.click(within(row).getByTestId('qty-annotation-trigger-row-moved-heading'));

    const dialog = screen.getByTestId('qty-annotation-row-moved-heading');
    expect(within(dialog).getByText('Moved by AutoCount')).toBeInTheDocument();
    expect(dialog.textContent ?? '').not.toMatch(/\bRedirected\b/);
  });
});

describe('Customer and Project print as two columns (PLAN-oi-worklist-split-customer-project.md, owner 18 Sep 2026)', () => {
  it('no column with id or accessorKey "project_customer" is on the list any more', () => {
    const allColumns = columnDefs();
    const ids = allColumns.map((column) => {
      const withKeys = column as ColumnDef<OrderInquiryWorklistRow> & {
        id?: string;
        accessorKey?: string;
      };
      return withKeys.id ?? withKeys.accessorKey;
    });
    expect(ids).not.toContain('project_customer');
    expect(ids).toContain('customer_name');
    expect(ids).toContain('project_title');
  });

  it('a long customer name truncates with a title tooltip', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-customer-long',
          customer_name: 'EXACO ENGINEERING AND CONSTRUCTION SDN BHD',
        }),
      ],
      'customer_name',
    );
    const cell = screen.getByText('EXACO ENGINEERING AND CONSTRUCTION SDN BHD');
    expect(cell.className).toContain('truncate');
    expect(cell.getAttribute('title')).toBe('EXACO ENGINEERING AND CONSTRUCTION SDN BHD');
  });

  it('a row with no customer party attached prints the empty state, not a blank cell', () => {
    renderRows([worklistRow({ id: 'row-customer-none', customer_name: null })], 'customer_name');
    expect(screen.getByText('Not attributed')).toBeInTheDocument();
  });

  it('a pre-order project title carries its PRE-ORDER note, truncated with a title tooltip', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-project-preorder',
          project_title: 'Bandar Puteri Phase 2 / PRE-ORDER',
        }),
      ],
      'project_title',
    );
    const cell = screen.getByText('Bandar Puteri Phase 2 / PRE-ORDER');
    expect(cell.className).toContain('truncate');
    expect(cell.getAttribute('title')).toBe('Bandar Puteri Phase 2 / PRE-ORDER');
  });

  it('an adopted row with no project prints "No project", not a blank cell', () => {
    renderRows([worklistRow({ id: 'row-project-none', project_title: null })], 'project_title');
    expect(screen.getByText('No project')).toBeInTheDocument();
  });
});

describe('the Raised at cell carries its own history in a tooltip (PLAN-oi-worklist-split-customer-project.md, owner 18 Sep 2026)', () => {
  it('a row with a prior raise shows the info icon, with "Previously raised" and one line per entry', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-raised-history',
          raised_at: '2026-08-15T10:00:00',
          raise_history: [
            { raised_at: '2026-08-01T09:15:00', raised_by_name: 'ZZT Farah' },
          ],
        }),
      ],
      'raised_at',
    );

    const row = screen.getByTestId('row-row-raised-history');
    expect(within(row).getByLabelText('Previously raised')).toBeInTheDocument();
    expect(within(row).getByText('Previously raised')).toBeInTheDocument();
    expect(within(row).getByText(/ZZT Farah/)).toBeInTheDocument();
  });

  it('a row with no history shows no info icon', () => {
    renderRows(
      [
        worklistRow({
          id: 'row-raised-no-history',
          raised_at: '2026-08-15T10:00:00',
          raise_history: [],
        }),
      ],
      'raised_at',
    );

    const row = screen.getByTestId('row-row-raised-no-history');
    expect(within(row).queryByLabelText('Previously raised')).not.toBeInTheDocument();
  });
});
