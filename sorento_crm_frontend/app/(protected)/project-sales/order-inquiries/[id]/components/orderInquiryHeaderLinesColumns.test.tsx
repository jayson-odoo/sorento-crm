/**
 * S3 (`PLAN-board-oi-mechanical-22sep.md`, AC-B3-1): the Lines tab's own columns - Product,
 * Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State -
 * with Taken/Remaining hideable through Columns like the rest of the grid. `SO line` is S6
 * (AC-B6-1), also asserted here since it sits in this same list; its own href/label
 * behaviour is `orderInquiryWorklist.test.ts`'s and `orderInquiryWorklistColumns.test.tsx`'s.
 *
 * Column-order list updated at the #1119 x oi-request-cs-reserve merge (22 Sep, cross-lane):
 * main's own version of this assertion predates a column this lane already shipped in
 * Phase 1 - `Expand` (the board stock-grid chevron, `PLAN-oi-request-cs-reserve.md` 3.9)
 * sits FIRST, before Product. Real, shipped, not a merge artefact.
 *
 * Round 3 (`PLAN-oi-request-cs-reserve.md` section 6d G2, AC-RS-68): the round-2 `Reserve`
 * column this list used to end with is retired - the State cell itself is the reserve
 * click target now (`AC-RS-68` suite below), so the census here drops back to one column
 * per fact.
 */
import { render, renderHook, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
import { useOrderInquiryHeaderLinesColumns } from './orderInquiryHeaderLinesColumns';
import type { OrderInquiryWorklistRow } from '../../../_shared/types/orderInquiry.types';

function headerTitleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

describe('AC-B3-1: the Lines tab reads Product, Qty, Taken, Remaining, Delivery date, Supplier, PO, SPO, Location, Instruction, State', () => {
  it('carries every named column, in order, after the select column', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const titles = result.current.map((column) => headerTitleOf(column)).filter(Boolean);

    expect(titles).toEqual([
      'Expand',
      'Product',
      'SO line',
      'Qty',
      'Taken',
      'Remaining',
      'Delivery date',
      'Supplier',
      'PO',
      'SPO',
      'Location',
      'Instruction',
      // AC-DT-6 (`PLAN-oi-decision-trail-ui.md`): the trail behind the instruction,
      // right after it. "Raised via", not "Raised" - the worklist already has a
      // "Raised by" column beside it (captain ruling, review round 1).
      'Raised via',
      'State',
    ]);
  });

  it('Taken and Remaining are hideable through Columns, the same as the rest of the grid', () => {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const taken = result.current.find((column) => headerTitleOf(column) === 'Taken') as
      | { enableHiding?: boolean }
      | undefined;
    const remaining = result.current.find((column) => headerTitleOf(column) === 'Remaining') as
      | { enableHiding?: boolean }
      | undefined;

    expect(taken).toBeDefined();
    expect(remaining).toBeDefined();
    // Only the select column opts out of hiding (`buildSelectColumn`'s own `enableHiding:
    // false`); Taken/Remaining carry no such flag, so they are hideable by the grid's
    // default the same way Supplier or Location already are.
    expect(taken?.enableHiding).not.toBe(false);
    expect(remaining?.enableHiding).not.toBe(false);
  });
});

function linesRow(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    verb: 'ORDER',
    state: 'raised',
    qty: '10',
    linked_qty: '0',
    bundled_qty: '0',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

/** Only the FOOTER row: the three sums are what this is about, and rendering the cells
 * would drag every per-cell dependency (documents dialog, state pill, links) into a test
 * that asserts none of them. */
function LinesFooter({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const columns = useOrderInquiryHeaderLinesColumns();
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <table>
      <tfoot>
        <tr>
          {table.getFooterGroups().flatMap((group) =>
            group.headers.map((header) => (
              <td key={header.id} data-testid={`footer-${header.column.id}`}>
                {header.column.columnDef.footer
                  ? flexRender(header.column.columnDef.footer, header.getContext())
                  : null}
              </td>
            )),
          )}
        </tr>
      </tfoot>
    </table>
  );
}

/**
 * AC-B3-4/AC-B3-5, review round 22 Sep (kill test): the Lines tab's OWN Qty footer had no
 * test of its own - only Taken/Remaining's shared footer did
 * (`orderInquiryWorklistColumns.test.tsx`) - so a Qty footer that summed EVERY loaded row
 * rather than the buy rows alone would have shipped green, printing a total that included
 * a notice row's quantity and a cancelled row's.
 */
describe('AC-B3-5: the Lines tab footers total the buy rows only', () => {
  it('excludes notice rows and cancelled rows from Qty, Taken and Remaining alike', () => {
    const buyRows = Array.from({ length: 10 }, (_unused, index) =>
      linesRow({ id: `buy-${index}`, qty: '10', linked_qty: '4' }),
    );
    render(
      <LinesFooter
        rows={[
          ...buyRows,
          // A notice row carries a quantity of its own and never a link: counted, it
          // would add 999 to Qty and 999 to Remaining.
          linesRow({ id: 'notice', verb: 'ADVANCE', qty: '999', linked_qty: '0' }),
          // A cancelled row is quantity the book called off: counted, it would add 500
          // to Qty and 250 to Taken.
          linesRow({
            id: 'cancelled',
            state: 'cancelled',
            qty: '500',
            linked_qty: '250',
          }),
        ]}
      />,
    );

    expect(screen.getByTestId('footer-qty')).toHaveTextContent(/^100$/);
    expect(screen.getByTestId('footer-taken')).toHaveTextContent(/^40$/);
    expect(screen.getByTestId('footer-remaining')).toHaveTextContent(/^60$/);
  });
});

/**
 * Round 4 (`PLAN-oi-request-cs-reserve.md` 6e) + AC-RS-83c (owner, 24 Sep: "this pen can
 * put right next to state?"): the State pill is plain text (never a button), and the
 * reserve icons render INSIDE the State cell to the right of it - no separate
 * `reserve_actions` column (saved column preferences appended an unknown id at the end,
 * after Location). Gated exactly as before: `canReserve` plus the line's reserve state.
 * `requested_qty` is cast onto the fixture: the local `linesRow` helper types only the
 * fields it sets.
 */
describe('AC-RS-83 / 83b / 83c: the reserve icons live inside the State cell', () => {
  function stateCell(
    row: OrderInquiryWorklistRow,
    options: Record<string, unknown> = {},
  ) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns(options as never));
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(stateColumn).toBeDefined();
    return stateColumn!.cell({ row: { original: row } });
  }

  const requestedRow = {
    ...linesRow({ id: 'row-req', state: 'raised', reserve_state: 'requested' }),
    requested_qty: '107',
  } as unknown as OrderInquiryWorklistRow;

  it('AC-RS-83c: no column carries id reserve_actions, with or without the permission', () => {
    for (const canReserve of [true, false]) {
      const { result } = renderHook(() =>
        useOrderInquiryHeaderLinesColumns({ canReserve } as never),
      );
      expect(
        result.current.some((column) => (column as { id?: string }).id === 'reserve_actions'),
      ).toBe(false);
    }
  });

  it('a requested row with the permission: pill text (not a button) + Reserve and Edit reserve in the same cell', () => {
    render(<>{stateCell(requestedRow, { canReserve: true })}</>);
    const pill = screen.getByText('Request to reserve 107');
    expect(pill.closest('button')).toBeNull();
    expect(screen.getByLabelText('Reserve')).toBeInTheDocument();
    expect(screen.getByLabelText('Edit reserve')).toBeInTheDocument();
  });

  it('AC-RS-83c: with the permission the State column starts at 380 wide with no minSize, so it can be narrowed back down', () => {
    const { result } = renderHook(() =>
      useOrderInquiryHeaderLinesColumns({ canReserve: true } as never),
    );
    const stateColumn = result.current.find(
      (column) => (column as { accessorKey?: string }).accessorKey === 'state',
    ) as { size?: number; minSize?: number };
    expect(stateColumn.size).toBe(380);
    expect(stateColumn.minSize).toBeUndefined();
  });

  it('without the permission: the pill only, no icons', () => {
    render(<>{stateCell(requestedRow, { canReserve: false })}</>);
    expect(screen.getByText('Request to reserve 107')).toBeInTheDocument();
    expect(screen.queryByLabelText('Reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
  });

  it('AC-RS-83b: a declined row reads Not reserved with Amend reserve + History beside it', () => {
    const declinedRow = linesRow({ id: 'row-decl', state: 'raised', reserve_state: 'declined' });
    render(<>{stateCell(declinedRow, { canReserve: true })}</>);
    expect(screen.getByText('Not reserved')).toBeInTheDocument();
    expect(screen.getByLabelText('Amend reserve')).toBeInTheDocument();
    expect(screen.getByLabelText('History')).toBeInTheDocument();
  });

  it('a line with no reserve state: the plain state pill, no icons', () => {
    render(<>{stateCell(linesRow({ id: 'row-plain', state: 'raised' }), { canReserve: true })}</>);
    expect(screen.queryByLabelText('Edit reserve')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amend reserve')).not.toBeInTheDocument();
  });

  it('a staged line shows the chip and Undo inside the State cell', () => {
    render(
      <>
        {stateCell(requestedRow, {
          canReserve: true,
          stagedByRowId: { 'row-req': { kind: 'reserve', qty: 107, locationLabel: 'BRW' } },
        })}
      </>,
    );
    expect(screen.getByText('Reserve 107 @ BRW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();
  });
});

describe('AC-DT-6: the Raised via column (PLAN-oi-decision-trail-ui.md)', () => {
  function raisedCell(row: OrderInquiryWorklistRow) {
    const { result } = renderHook(() => useOrderInquiryHeaderLinesColumns());
    const raisedColumn = result.current.find(
      (column) => (column as { id?: string }).id === 'raise_event',
    ) as { cell: (context: unknown) => React.ReactNode } | undefined;
    expect(raisedColumn).toBeDefined();
    return raisedColumn!.cell({ row: { original: row } });
  }

  it('reads "Reconfirmed by <name> · <date time>" for a matched reconfirm event', () => {
    render(
      <>
        {raisedCell(
          linesRow({
            raise_event_kind: 'reconfirmed',
            raise_event_by_name: 'Nurain',
            raise_event_at: '2026-09-25T01:20:34',
          }),
        )}
      </>,
    );
    expect(screen.getByText(/Reconfirmed by Nurain/)).toBeInTheDocument();
  });

  it('reads "Raised by <name> · <date time>" for a matched raise event', () => {
    render(
      <>
        {raisedCell(
          linesRow({
            raise_event_kind: 'raised',
            raise_event_by_name: 'Johnson',
            raise_event_at: '2026-09-20T03:22:00',
          }),
        )}
      </>,
    );
    expect(screen.getByText(/Raised by Johnson/)).toBeInTheDocument();
  });

  it('reads "Sheet" for a row whose note starts with the sheet migration stamp, no event matched', () => {
    render(
      <>
        {raisedCell(
          linesRow({
            raise_event_kind: null,
            note: 'Migrated from order inquiry sheet, row 42',
          }),
        )}
      </>,
    );
    expect(screen.getByText('Sheet')).toBeInTheDocument();
  });

  it('reads "Planning change" for a row whose note carries the date-move stamp, no event matched', () => {
    render(
      <>
        {raisedCell(
          linesRow({
            raise_event_kind: null,
            note: 'Was 2026-09-01',
          }),
        )}
      </>,
    );
    expect(screen.getByText('Planning change')).toBeInTheDocument();
  });

  it('reads a dash when nothing at all is known about how the row was raised', () => {
    render(<>{raisedCell(linesRow({ raise_event_kind: null, note: null }))}</>);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  // Reviewer B1, round 1: on the 24 Sep prod copy 10,246 sheet-migrated rows also match
  // migration 523's anonymous backfill `raised` event and 2,070 more latch onto a reconfirm
  // hours later - the note's own sheet stamp is the fact, and it outranks any event.
  it('reads a bare "Sheet" - no by, no date - for a sheet-migrated row even when an event matched it', () => {
    render(
      <>
        {raisedCell(
          linesRow({
            raise_event_kind: 'reconfirmed',
            raise_event_by_name: 'Jayson Foundryx',
            raise_event_at: '2026-09-25T04:00:00',
            note: 'Migrated from order inquiry sheet, row 42',
          }),
        )}
      </>,
    );
    expect(screen.getByText('Sheet')).toBeInTheDocument();
    expect(screen.queryByText(/Reconfirmed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Jayson/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();
  });

  // Reviewer S2, round 1: an ORDINARY raise/reconfirm note also starts with "Was" -
  // `Was {qty} on {date}` / `Was {qty}, no previous delivery date`
  // (project_order_inquiry_service.py, the import service). Only what
  // planning_change_service.py itself writes reads Planning change.
  it('does NOT read Planning change for an ordinary "Was 5 on 2026-09-01" raise note', () => {
    render(<>{raisedCell(linesRow({ raise_event_kind: null, note: 'Was 5 on 2026-09-01' }))}</>);
    expect(screen.queryByText('Planning change')).not.toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('does NOT read Planning change for "Was 5, no previous delivery date"', () => {
    render(
      <>
        {raisedCell(
          linesRow({ raise_event_kind: null, note: 'Was 5, no previous delivery date' }),
        )}
      </>,
    );
    expect(screen.queryByText('Planning change')).not.toBeInTheDocument();
  });

  it('reads Planning change for the date-move stamp "No previous delivery date"', () => {
    render(
      <>{raisedCell(linesRow({ raise_event_kind: null, note: 'No previous delivery date' }))}</>,
    );
    expect(screen.getByText('Planning change')).toBeInTheDocument();
  });

  it('reads Planning change for the qty-drop stamp "Was 5, now 3"', () => {
    render(<>{raisedCell(linesRow({ raise_event_kind: null, note: 'Was 5, now 3' }))}</>);
    expect(screen.getByText('Planning change')).toBeInTheDocument();
  });
});
